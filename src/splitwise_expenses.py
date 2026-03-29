# API Call to splitwise
import hashlib
import os
import re
from splitwise import Splitwise
import logging
import pandas as pd
from read_yaml_config import read_yaml_config
from pathlib import Path
from datetime import datetime, date as date_type

_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}')


def _expense_content_hash(expense) -> str:
    """Stable hash of the fields that matter for YNAB sync.
    Unchanged recurring expenses hash identically across re-stamps;
    a genuine edit (amount, split, description) produces a different hash.
    """
    parts = [
        (expense.getDate() or '')[:10],
        expense.getCost() or '',
        expense.getDescription() or '',
    ]
    for user in sorted(expense.getUsers(), key=lambda u: u.getFirstName() or ''):
        parts.append(f"{user.getFirstName()}:{user.getPaidShare()}:{user.getOwedShare()}")
    return hashlib.md5('|'.join(parts).encode()).hexdigest()

#config_file_path = 'config/config.yaml'
#config = read_yaml_config(config_file_path)

class SplitwiseExpenses():
    def __init__(self,config,update_after):
        consumer_key = config['splitwise_api']['consumer_key']
        consumer_secret = config['splitwise_api']['consumer_secret']
        api_key = config['splitwise_api']['api_key']
        self.s = Splitwise(consumer_key,consumer_secret,api_key=api_key)

        from_date = config['splitwise_api']['expenses']['from_date']
        if isinstance(from_date, str):
            try:
                from_date = datetime.strptime(from_date, '%Y-%m-%d').date()
            except ValueError:
                raise ValueError(f"'from_date' must be in YYYY-MM-DD format, got: {from_date!r}")
        elif not isinstance(from_date, date_type):
            raise ValueError(f"'from_date' must be a date or YYYY-MM-DD string, got: {type(from_date)}")

        if update_after is not None:
            self.expenses = self.s.getExpenses(limit = 500,
                                            dated_after=from_date.isoformat(),
                                            updated_after=update_after.isoformat())
        else:
            self.expenses = self.s.getExpenses(limit = 500,
                                            dated_after=from_date.isoformat())
        self.update_after = update_after

    def get_expenses_dataframe(self):
        # Fetch expenses using the Splitwise API instance
        
        # Create lists to store the date, amount, and payer information
        dates = []
        amounts = []
        loaners = []
        borrowers = []
        descriptions = []
        
        # Process each expense
        for expense in self.expenses:
            dates.append(expense.getDate())
            amounts.append(expense.getCost())
            
            # Find the loaner (the one who paid)
            loaner = next((user.getFirstName() for user in expense.getUsers() if float(user.getPaidShare()) > 0), "Unknown")
            loaners.append(loaner)
            
            # Find the borrower(s) (those who owe a share)
            borrower_info = [
                f"{user.getFirstName()} (EUR{float(user.getOwedShare()):.2f})"
                for user in expense.getUsers() if float(user.getOwedShare()) > 0
            ]
            borrowers.append(", ".join(borrower_info))  # Join borrowers and their shares as a comma-separated string

            # Add the memo (if any) to the memo list
            descriptions.append(expense.getDescription() if expense.getDescription() else "")
        
        # Create a DataFrame from the collected data
        df = pd.DataFrame({
            'Date': dates,
            'Amount': amounts,
            'Loaner': loaners,
            'Borrowers': borrowers,
            'Description': descriptions
        })
        return df
    
    def get_borrowed_expenses_by_user(self, user_name: str, processed_expenses: dict = None):
        """
        Returns borrowed expenses for user_name.

        processed_expenses: optional dict mapping str(expense_id) -> content_hash
                            for expenses synced in previous runs.
                            - ID not in dict  → new expense, include it
                            - ID in dict, hash unchanged → already synced, skip
                            - ID in dict, hash changed  → expense was edited, re-sync
        """
        # List to store relevant expense data
        expense_data = []

        for expense in self.expenses:
            # Skip if already synced and content is unchanged.
            # processed_expenses values may be a plain hash string (legacy) or
            # {"hash": str, "ynab_ids": [...]} (current format).
            expense_id = str(expense.getId())
            current_hash = _expense_content_hash(expense)
            if processed_expenses:
                stored = processed_expenses.get(expense_id)
                if stored is not None:
                    stored_hash = stored['hash'] if isinstance(stored, dict) else stored
                    if stored_hash == current_hash:
                        continue

            # Determine the description
            description = expense.getDescription() if expense.getDescription() else ""

            # Skip payments (debt settlements, not real expenses)
            if description == 'Payment':
                continue

            # Validate and extract the expense date
            date_raw = expense.getDate()
            if not _DATE_RE.match(date_raw):
                raise ValueError(f"Unexpected date format from Splitwise API: {date_raw!r}")
            expense_date = date_raw[:10]

            # Find all net creditors (users who paid more than their own share)
            creditors = [
                u for u in expense.getUsers()
                if float(u.getPaidShare()) - float(u.getOwedShare()) > 0
            ]

            # Skip if the target user is among the creditors (they paid, not owed)
            if any(c.getFirstName().lower() == user_name.lower() for c in creditors):
                continue

            # Find the target user's owed share
            user_share = None
            for user in expense.getUsers():
                if user.getFirstName().lower() == user_name.lower() and float(user.getOwedShare()) > 0:
                    user_share = float(user.getOwedShare())
                    break

            if user_share is None:
                continue

            # Split the owed share across all creditors proportionally to their
            # net contribution, creating one row per creditor.
            total_net_credit = sum(
                float(c.getPaidShare()) - float(c.getOwedShare()) for c in creditors
            )
            for creditor in creditors:
                net = float(creditor.getPaidShare()) - float(creditor.getOwedShare())
                proportion = net / total_net_credit if total_net_credit > 0 else 1.0
                expense_data.append({
                    'expense_id': expense_id,
                    'expense_hash': current_hash,
                    'Date': expense_date,
                    'Loaner': creditor.getFirstName(),
                    'Amount': float(expense.getCost()),
                    'Description': description,
                    'Borrower': user_name,
                    'Share': round(user_share * proportion, 2)
                })

        # Create DataFrame from the list of dictionaries
        df = pd.DataFrame(expense_data)

        if df.empty:
            print(f"No borrowed expenses found for user '{user_name}'.")

        return df

    def create_ynab_expense_file_from_df(self, user_name: str, processed_expenses: dict = None):
        # Define output path and add the timestamp to the filename
        output_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output", f"borrowed_expenses_{user_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv") # Add the timestamp to the name

        df = self.get_borrowed_expenses_by_user(user_name, processed_expenses=processed_expenses)

        if df.empty:
            print(f"No borrowed expenses found for user {user_name} that were updated after {self.update_after}")
            return
        
        # Initialize total borrowed amount
        total_borrowed = df['Share'].sum()
        first_date = df['Date'].min()

        # Modify the DataFrame to fit YNAB's schema
        df_ynab = pd.DataFrame({
            'Date': df['Date'],
            'Payee': df['Loaner'],
            'Category': '',  # Leave category blank
            'Memo': 'Virtual Expense: ' + df['Description'],
            'Outflow': df['Share'],
            'Inflow': ''  # Leave inflow blank for each borrowed expense
        })
        
        # Add a final row for the total borrowed amount as an inflow
        total_row = pd.DataFrame({
            'Date': [first_date],
            'Payee': ['Total Virtual Inflow'],
            'Category': [''],
            'Memo': ['Total amount borrowed'],
            'Outflow': [''],
            'Inflow': [total_borrowed]
        })
        
        # Append the total row to the main DataFrame
        df_ynab = pd.concat([df_ynab, total_row], ignore_index=True)
        
        # Write the DataFrame to a CSV file at the output path
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        df_ynab.to_csv(output_path, index=False)

        print(f"YNAB-compatible CSV file created at {output_path}")