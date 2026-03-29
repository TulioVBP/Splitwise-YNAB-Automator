import json
import os
import logging
from splitwise_expenses import SplitwiseExpenses
from read_yaml_config import read_yaml_config
from get_latest_timestamp_for_user import get_latest_timestamp_for_user
from ynab_expenses import YNABExpenses

def main():
    # Config
    config_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),'config/config.yaml')
    config = read_yaml_config(config_file_path)
    
    # Output dir
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
    
    # Debugging
    logging.basicConfig(level=logging.DEBUG)
    
    # Selecting user and retrieving latest run
    user_name = config['splitwise_api']['expenses']['user_name']
    _, latest_timestamp = get_latest_timestamp_for_user(output_dir, user_name)

    # Load {expense_id: {"hash": str, "ynab_ids": [str]}} for expenses synced in
    # previous runs.  Migrate legacy format (plain hash string) transparently.
    # Skip if hash matches (recurring re-stamp); re-sync if hash differs (genuine edit).
    expenses_file = os.path.join(output_dir, f"processed_expenses_{user_name}.json")
    processed_expenses = {}
    if os.path.exists(expenses_file):
        with open(expenses_file) as f:
            raw = json.load(f)
        processed_expenses = {
            k: (v if isinstance(v, dict) else {"hash": v, "ynab_ids": []})
            for k, v in raw.items()
        }

    # Splitwise Obj
    s = SplitwiseExpenses(config, latest_timestamp)

    # YNAB Object
    ynab_token = config['ynab_api']['token']
    budget_id = config['ynab_api']['budget_id']
    account_id = config['ynab_api']['account_id']
    categories = config['ynab_api']['categories']
    ynab = YNABExpenses(ynab_token, budget_id, account_id, categories)

    # Adding expenses to YNAB
    expenses_df = s.get_borrowed_expenses_by_user(user_name, processed_expenses=processed_expenses)
    if expenses_df.empty:
        print("No expenses to add to YNAB.")
        return

    # Updated expenses (ID already known) must not have their hash saved until
    # accepted — otherwise a skipped update is permanently lost.
    updated_ids = set(expenses_df['expense_id']) & set(processed_expenses.keys())
    new_expenses = expenses_df[~expenses_df['expense_id'].isin(updated_ids)]

    # Partial-run guard: commit CSV and save hashes for NEW expenses only.
    s.create_ynab_expense_file_from_df(user_name, processed_expenses=processed_expenses)
    os.makedirs(output_dir, exist_ok=True)
    processed_expenses.update(
        {row['expense_id']: {"hash": row['expense_hash'], "ynab_ids": []}
         for _, row in new_expenses.iterrows()}
    )
    with open(expenses_file, 'w') as f:
        json.dump(processed_expenses, f)

    print("Proceeding to add expenses to YNAB...")
    print(f"Expenses DataFrame:\n{expenses_df.head()}")
    for row in expenses_df.itertuples():
        print(f"Do you want to add the following expense to YNAB?")
        print(f"Date: {row.Date}, Amount: {row.Share}, Description: {row.Description}, Loaner: {row.Loaner}")
        user_input = input("Type 'yes' to proceed or 'no' to skip: ").strip().lower()
        if user_input != 'yes':
            print("Skipping this expense.")
            continue
        try:
            eid = str(row.expense_id)
            if eid in updated_ids:
                # Delete the previously synced YNAB transaction(s) for this expense
                # before creating the updated version, to avoid duplicates.
                old_ynab_ids = processed_expenses.get(eid, {}).get("ynab_ids", [])
                if old_ynab_ids:
                    ynab.delete_transactions(old_ynab_ids)
            new_ynab_ids = ynab.add_expenses(
                expenses_df[row.Index:row.Index+1], approved=False
            )
            # Save hash and new YNAB IDs only after successful submission.
            if eid in updated_ids:
                processed_expenses[eid] = {"hash": row.expense_hash, "ynab_ids": new_ynab_ids}
                with open(expenses_file, 'w') as f:
                    json.dump(processed_expenses, f)
        except Exception as e:
            print(f"Error adding expenses to YNAB: {e}")
            return
    print(f"Expenses added to YNAB successfully. Data saved to {output_dir}.")

if __name__ == "__main__":
    main() 