import os
import re
from datetime import datetime

def get_latest_timestamp_for_user(output_dir: str, user_name: str):
    # Define the regex pattern to match filenames with the given user name
    pattern = rf".*_{user_name}_(\d{{8}})_(\d{{4}})\.csv$"
    
    # Initialize variable to keep track of the latest timestamp
    latest_timestamp = None
    latest_file = None

    # Iterate through files in the output directory
    for file_name in os.listdir(output_dir):
        # Match the file name with the regex pattern
        match = re.match(pattern, file_name)
        if match:
            # Extract date and time from the filename
            date_str, time_str = match.groups()
            timestamp_str = f"{date_str}_{time_str}"
            
            # Convert to datetime object
            timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M")
            
            # Update the latest timestamp and file if this one is newer
            if latest_timestamp is None or timestamp > latest_timestamp:
                latest_timestamp = timestamp
                latest_file = file_name

    if latest_timestamp:
        print(f"Latest file for user {user_name}: {latest_file} with timestamp {latest_timestamp}")
    else:
        print(f"No files found for user {user_name} in the directory.")
    
    return latest_file, latest_timestamp

# Usage example
# output_dir = "../output"  # Define the path to the output directory
# user_name = "John"
# latest_file, latest_timestamp = get_latest_timestamp_for_user(output_dir, user_name)
