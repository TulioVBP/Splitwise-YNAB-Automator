import pandas as pd
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
    
    # Splitwise Obj
    s = SplitwiseExpenses(config, latest_timestamp)

    # YNAB Object
    ynab_token = config['ynab_api']['token']
    budget_id = config['ynab_api']['budget_id']
    account_id = config['ynab_api']['account_id']
    categories = config['ynab_api']['categories']
    ynab = YNABExpenses(ynab_token, budget_id, account_id, categories)

    # Adding expenses to YNAB
    expenses_df = s.get_borrowed_expenses_by_user("Tulio")
    if expenses_df.empty:
        print("No expenses to add to YNAB.")
        return
    # 1. Ask if user wants to proceed with the following line
    print("Proceeding to add expenses to YNAB...")
    print(f"Expenses DataFrame:\n{expenses_df.head()}")
    for row in expenses_df.itertuples():
        print(f"Do you want to add the following expense to YNAB?")
        print(f"Date: {row.Date}, Amount: {row.Share}, Description: {row.Description}, Loaner: {row.Loaner}")
        user_input = input("Type 'yes' to proceed or 'no' to skip: ").strip().lower()
        if user_input != 'yes':
            print("Skipping this expense.")
            continue
        # 2. Add expenses to YNAB
        try:
            response = ynab.add_expenses(expenses_df[row.Index:row.Index+1])
        except Exception as e:
            print(f"Error adding expenses to YNAB: {e}")
            return
    # Saving the DataFrame to a CSV file
    s.create_ynab_expense_file_from_df(user_name)
    print(f"Expenses added to YNAB successfully. Data saved to {output_dir}.")

if __name__ == "__main__":
    main() 