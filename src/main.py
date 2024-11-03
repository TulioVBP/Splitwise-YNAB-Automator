import pandas as pd
from pathlib import Path
import os

from splitwise_expenses import SplitwiseExpenses
import logging
import pandas as pd
from read_yaml_config import read_yaml_config
from get_latest_timestamp_for_user import get_latest_timestamp_for_user


# Config
config_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)),'config/config.yaml')
config = read_yaml_config(config_file_path)

# Output dir
output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output") # Add the timestamp to the name

# Debugging
logging.basicConfig(level=logging.DEBUG)

# Selecting user and retrieving latest run
user_name = config['splitwise_api']['expenses']['user_name']
latest_file, latest_timestamp = get_latest_timestamp_for_user(output_dir, user_name)

# Splitwise Obj
s = SplitwiseExpenses(config, latest_timestamp)
s.create_ynab_expense_file_from_df(user_name)

# YNAB Obj


# Create the 
