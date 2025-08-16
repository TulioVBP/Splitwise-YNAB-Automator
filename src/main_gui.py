import PySimpleGUI as sg
import os
import yaml
import pandas as pd
from splitwise_expenses import SplitwiseExpenses
from read_yaml_config import read_yaml_config
from get_latest_timestamp_for_user import get_latest_timestamp_for_user

# PySimpleGUI version
def main():
    config_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config/config.yaml')
    config = read_yaml_config(config_file_path)
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")

    sg.theme('SystemDefault')
    layout = [
        [sg.Text('Budget Simplifier', font=("Arial", 16, "bold"), justification='center', expand_x=True)],
        [sg.Text(f"Current User: {config['splitwise_api']['expenses']['user_name']}", key='-USER-', font=("Arial", 12))],
        [sg.Button('Retrieve Latest Debts', key='-DEBTS-', size=(25, 1))],
        [sg.Button('Retrieve Latest Credits', key='-CREDITS-', size=(25, 1))],
        [sg.Button('Change User Name', key='-CHANGEUSER-', size=(25, 1))],
        [sg.Text('Ready', key='-STATUS-', text_color='green', size=(40, 1))]
    ]
    window = sg.Window('Budget Simplifier', layout, finalize=True)

    while True:
        event, values = window.read()
        if event == sg.WIN_CLOSED:
            break
        elif event == '-DEBTS-':
            window['-STATUS-'].update('Retrieving debts...', text_color='orange')
            window.refresh()
            try:
                user_name = config['splitwise_api']['expenses']['user_name']
                latest_file, latest_timestamp = get_latest_timestamp_for_user(output_dir, user_name)
                s = SplitwiseExpenses(config, latest_timestamp)
                s.create_ynab_expense_file_from_df(user_name)
                window['-STATUS-'].update('Debts retrieved successfully!', text_color='green')
                sg.popup('Success', f'Debts for {user_name} have been retrieved and saved to output folder.')
            except Exception as e:
                window['-STATUS-'].update('Error retrieving debts', text_color='red')
                sg.popup_error('Error', f'Failed to retrieve debts: {str(e)}')
        elif event == '-CREDITS-':
            window['-STATUS-'].update('Retrieving credits...', text_color='orange')
            window.refresh()
            try:
                user_name = config['splitwise_api']['expenses']['user_name']
                latest_file, latest_timestamp = get_latest_timestamp_for_user(output_dir, user_name)
                s = SplitwiseExpenses(config, latest_timestamp)
                df = s.get_expenses_dataframe()
                credits_df = df[df['Loaner'] == user_name]
                if not credits_df.empty:
                    output_path = os.path.join(output_dir, f"credits_{user_name}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv")
                    credits_df.to_csv(output_path, index=False)
                    window['-STATUS-'].update('Credits retrieved successfully!', text_color='green')
                    sg.popup('Success', f'Credits for {user_name} have been retrieved and saved to output folder.')
                else:
                    window['-STATUS-'].update('No credits found', text_color='orange')
                    sg.popup('Info', f'No credits found for {user_name}.')
            except Exception as e:
                window['-STATUS-'].update('Error retrieving credits', text_color='red')
                sg.popup_error('Error', f'Failed to retrieve credits: {str(e)}')
        elif event == '-CHANGEUSER-':
            current_user = config['splitwise_api']['expenses']['user_name']
            new_user = sg.popup_get_text(f'Current user: {current_user}\nEnter new user name:')
            if new_user and new_user.strip():
                try:
                    config['splitwise_api']['expenses']['user_name'] = new_user.strip()
                    with open(config_file_path, 'w') as file:
                        yaml.dump(config, file, default_flow_style=False)
                    window['-USER-'].update(f"Current User: {new_user.strip()}")
                    window['-STATUS-'].update('User name updated successfully!', text_color='green')
                    sg.popup('Success', f'User name changed to: {new_user.strip()}')
                except Exception as e:
                    window['-STATUS-'].update('Error updating user name', text_color='red')
                    sg.popup_error('Error', f'Failed to update user name: {str(e)}')
    window.close()

if __name__ == "__main__":
    main()