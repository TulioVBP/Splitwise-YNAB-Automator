import pandas as pd
import os
import logging
from splitwise_expenses import SplitwiseExpenses
from read_yaml_config import read_yaml_config
from get_latest_timestamp_for_user import get_latest_timestamp_for_user
from ynab_expenses import add_expenses_to_ynab

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
    latest_file, latest_timestamp = get_latest_timestamp_for_user(output_dir, user_name)
    
    # Splitwise Obj
    s = SplitwiseExpenses(config, latest_timestamp)
    s.create_ynab_expense_file_from_df(user_name)
    
    print(f"Expenses retrieved for {user_name}")

    # Add expenses to YNAB
    ynab_token = config['ynab_api']['token']
    budget_id = config['ynab_api']['budget_id']
    account_id = config['ynab_api']['account_id']
    categories = config['ynab_api']['categories']
    expenses_df = s.get_expenses_dataframe()
    response = add_expenses_to_ynab(ynab_token, budget_id, account_id, categories, expenses_df)
    print(f"Expenses added to YNAB: {response}")

if __name__ == "__main__":
    main() 