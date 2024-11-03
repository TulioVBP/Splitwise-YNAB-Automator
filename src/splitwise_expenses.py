# API Call to splitwise
import os
from splitwise import Splitwise
import logging
import pandas as pd
from read_yaml_config import read_yaml_config
from pathlib import Path
from datetime import datetime

#config_file_path = 'config/config.yaml'
#config = read_yaml_config(config_file_path)

class SplitwiseExpenses():
    def __init__(self,config,update_after):
        consumer_key = config['splitwise_api']['consumer_key']
        consumer_secret = config['splitwise_api']['consumer_secret']
        api_key = config['splitwise_api']['api_key']
        self.s = Splitwise(consumer_key,consumer_secret,api_key=api_key)
        if update_after is not None:
            self.expenses = self.s.getExpenses(limit = 50,
                                            dated_after=config['splitwise_api']['expenses']['from_date'].isoformat(),
                                            updated_after=update_after.isoformat())
        else:
            self.expenses = self.s.getExpenses(limit = 50,
                                            dated_after=config['splitwise_api']['expenses']['from_date'].isoformat())
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
    
    def get_borrowed_expenses_by_user(self, user_name: str):
        
        # List to store relevant expense data
        expense_data = []

        for expense in self.expenses:
            # Determine the loaner (the one who paid for the expense)
            loaner = next((user.getFirstName() for user in expense.getUsers() if float(user.getPaidShare()) > 0), "Unknown")
            
            # Determine the description
            description = expense.getDescription() if expense.getDescription() else ""
            
            # Skip this expense if the user is both the loaner and borrower
            if loaner == user_name:
                continue
            
            # Skip this expense if the description is 'Payment'
            if description == 'Payment':
                continue
            
            # Check if the specified user is a borrower
            user_share = None
            for user in expense.getUsers():
                # If the user_name is a borrower with an owed share, capture the share
                if user.getFirstName() == user_name and float(user.getOwedShare()) > 0:
                    user_share = float(user.getOwedShare())
                    break  # No need to check other users if we've found the target borrower
            
            # Only add the expense if user_name is a borrower
            if user_share is not None:
                expense_data.append({
                    'Date': expense.getDate()[0:10],
                    'Loaner': loaner,
                    'Amount': float(expense.getCost()),
                    'Description': expense.getDescription(),
                    'Borrower': user_name,
                    'Share': user_share
                })

        # Create DataFrame from the list of dictionaries
        df = pd.DataFrame(expense_data)
        
        return df

    def create_ynab_expense_file_from_df(self, user_name: str):
        # Define output path and add the timestamp to the filename
        #output_path = Path(f"../output/borrowed_expenses_{user_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv")  # Add the timestamp to the name
        output_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output", f"borrowed_expenses_{user_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv") # Add the timestamp to the name

        df = self.get_borrowed_expenses_by_user(user_name)

        if df.empty:
            print(f"No borrowed expenses found for user {user_name} that were updated after {self.update_after}")
            return
        
        # Initialize total borrowed amount
        total_borrowed = df['Share'].sum()
        last_date = df['Date'].max()

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
            'Date': [last_date],
            'Payee': ['Total Virtual Inflow'],
            'Category': [''],
            'Memo': ['Total amount borrowed'],
            'Outflow': [''],
            'Inflow': [total_borrowed]
        })
        
        # Append the total row to the main DataFrame
        df_ynab = pd.concat([df_ynab, total_row], ignore_index=True)
        
        # Write the DataFrame to a CSV file at the output path
        #os.makedirs(os.path.dirname(output_path), exist_ok=True)
        df_ynab.to_csv(output_path, index=False)

        print(f"YNAB-compatible CSV file created at {output_path}")