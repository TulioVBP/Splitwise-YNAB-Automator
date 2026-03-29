import json
import FreeSimpleGUI as sg
import os
import traceback
import yaml
import pandas as pd
from splitwise_expenses import SplitwiseExpenses
from read_yaml_config import read_yaml_config
from get_latest_timestamp_for_user import get_latest_timestamp_for_user
from ynab_expenses import YNABExpenses


def _review_expenses(expenses_df, categories):
    """Open a per-expense review window. Returns a list of accepted rows,
    each augmented with the user-selected category_id (or None)."""
    category_names = [c['name'] for c in categories]
    category_map = {c['name']: c['category_id'] for c in categories}
    total = len(expenses_df)
    accepted = []

    for idx in range(total):
        row = expenses_df.iloc[idx]
        layout = [
            [sg.Text(f'Review Expense ({idx + 1} of {total})', font=('Arial', 12, 'bold'))],
            [sg.HorizontalSeparator()],
            [sg.Text('Date:',        size=(12, 1)), sg.Text(str(row['Date']))],
            [sg.Text('From:',        size=(12, 1)), sg.Text(str(row['Loaner']))],
            [sg.Text('Description:', size=(12, 1)), sg.Text(str(row['Description']))],
            [sg.Text('Amount:',      size=(12, 1)), sg.Text(f"€{row['Share']:.2f}")],
            [sg.HorizontalSeparator()],
            [sg.Text('Category (optional):', size=(18, 1)),
             sg.Combo([''] + category_names, default_value='', key='-CAT-', size=(28, 1), readonly=True)],
            [sg.Text('')],
            [sg.Button('Skip', key='-SKIP-', size=(10, 1)),
             sg.Push(),
             sg.Button('Add to YNAB', key='-ADD-', size=(12, 1), button_color=('white', '#2e7d32'))],
        ]
        window = sg.Window('Review Expense', layout, modal=True, finalize=True)
        event, values = window.read()
        window.close()

        if event == '-ADD-':
            row_df = expenses_df.iloc[[idx]].copy()
            selected = values.get('-CAT-', '')
            row_df['category_id'] = category_map.get(selected) if selected else None
            accepted.append(row_df)

    return accepted


def main():
    config_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config/config.yaml')
    config = read_yaml_config(config_file_path)
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')

    sg.theme('SystemDefault')
    layout = [
        [sg.Text('Budget Simplifier', font=('Arial', 16, 'bold'), justification='center', expand_x=True)],
        [sg.Text(f"Current User: {config['splitwise_api']['expenses']['user_name']}", key='-USER-', font=('Arial', 12))],
        [sg.Button('Retrieve Latest Debts',   key='-DEBTS-',      size=(25, 1))],
        [sg.Button('Retrieve Latest Credits', key='-CREDITS-',    size=(25, 1))],
        [sg.Button('Change User Name',        key='-CHANGEUSER-', size=(25, 1))],
        [sg.Text('Ready', key='-STATUS-', text_color='green', size=(40, 1))],
    ]
    window = sg.Window('Budget Simplifier', layout, finalize=True)

    while True:
        event, values = window.read()
        if event == sg.WIN_CLOSED:
            break

        elif event == '-DEBTS-':
            window['-STATUS-'].update('Fetching debts from Splitwise...', text_color='orange')
            window.refresh()
            try:
                user_name = config['splitwise_api']['expenses']['user_name']
                _, latest_timestamp = get_latest_timestamp_for_user(output_dir, user_name)

                expenses_file = os.path.join(output_dir, f'processed_expenses_{user_name}.json')
                processed_expenses = {}
                if os.path.exists(expenses_file):
                    with open(expenses_file) as f:
                        raw = json.load(f)
                    processed_expenses = {
                        k: (v if isinstance(v, dict) else {"hash": v, "ynab_ids": []})
                        for k, v in raw.items()
                    }

                s = SplitwiseExpenses(config, latest_timestamp)
                expenses_df = s.get_borrowed_expenses_by_user(user_name, processed_expenses=processed_expenses)

                if expenses_df.empty:
                    window['-STATUS-'].update('No new debts found.', text_color='green')
                    sg.popup('Info', f'No new debts found for {user_name}.')
                    continue

                # Identify which expenses are genuinely new vs re-fetched due to an edit.
                # Updated expenses (ID already known) must not have their hash saved until
                # the user explicitly accepts them — otherwise a skipped update is lost forever.
                updated_ids = set(expenses_df['expense_id']) & set(processed_expenses.keys())
                new_expenses = expenses_df[~expenses_df['expense_id'].isin(updated_ids)]

                # Partial-run guard: commit CSV and save hashes for NEW expenses only.
                # If the app crashes before YNAB calls, new expenses won't be re-fetched.
                s.create_ynab_expense_file_from_df(user_name, processed_expenses=processed_expenses)
                os.makedirs(output_dir, exist_ok=True)
                processed_expenses.update(
                    {row['expense_id']: {"hash": row['expense_hash'], "ynab_ids": []}
                     for _, row in new_expenses.iterrows()}
                )
                with open(expenses_file, 'w') as f:
                    json.dump(processed_expenses, f)

                # Build YNAB client (inflow_default_category list passed so add_expenses
                # can assign the reimbursement category to the inflow subtransaction)
                ynab = YNABExpenses(
                    config['ynab_api']['token'],
                    config['ynab_api']['budget_id'],
                    config['ynab_api']['account_id'],
                    config['ynab_api'].get('categories', []),
                )
                window['-STATUS-'].update('Fetching YNAB categories...', text_color='orange')
                window.refresh()
                try:
                    live_categories = ynab.get_categories()
                except Exception as e:
                    traceback.print_exc()
                    live_categories = config['ynab_api'].get('categories', [])
                    sg.popup_error('Warning', f'Could not fetch YNAB categories, falling back to config.\n{e}')

                # Per-expense review
                window['-STATUS-'].update(
                    f'Reviewing {len(expenses_df)} expense(s)...', text_color='orange'
                )
                window.refresh()
                accepted = _review_expenses(expenses_df, live_categories)

                if not accepted:
                    window['-STATUS-'].update('All expenses skipped.', text_color='orange')
                    continue
                errors = []
                for row_df in accepted:
                    try:
                        eid = str(row_df.iloc[0]['expense_id'])
                        if eid in updated_ids:
                            # Delete the previously synced YNAB transaction(s) for this
                            # expense before creating the updated version (no duplicates).
                            old_ynab_ids = processed_expenses.get(eid, {}).get("ynab_ids", [])
                            if old_ynab_ids:
                                ynab.delete_transactions(old_ynab_ids)
                        new_ynab_ids = ynab.add_expenses(row_df, approved=False)
                        # Save updated hash and new YNAB IDs only after successful
                        # submission, so a skipped or failed update re-appears next run.
                        if eid in updated_ids:
                            processed_expenses[eid] = {
                                "hash": row_df.iloc[0]['expense_hash'],
                                "ynab_ids": new_ynab_ids,
                            }
                            with open(expenses_file, 'w') as f:
                                json.dump(processed_expenses, f)
                    except Exception as e:
                        traceback.print_exc()
                        desc = row_df.iloc[0].get('Description', '?')
                        errors.append(f'{desc}: {e}')

                if errors:
                    window['-STATUS-'].update('Done with errors.', text_color='red')
                    sg.popup_error('Some expenses failed to submit:\n' + '\n'.join(errors))
                else:
                    window['-STATUS-'].update(
                        f'{len(accepted)} expense(s) added to YNAB.', text_color='green'
                    )
                    sg.popup('Success', f'{len(accepted)} of {len(expenses_df)} expense(s) added to YNAB.')

            except Exception as e:
                traceback.print_exc()
                window['-STATUS-'].update('Error retrieving debts.', text_color='red')
                sg.popup_error('Error', f'Failed to retrieve debts: {e}')

        elif event == '-CREDITS-':
            window['-STATUS-'].update('Retrieving credits...', text_color='orange')
            window.refresh()
            try:
                user_name = config['splitwise_api']['expenses']['user_name']
                _, latest_timestamp = get_latest_timestamp_for_user(output_dir, user_name)
                s = SplitwiseExpenses(config, latest_timestamp)
                df = s.get_expenses_dataframe()
                credits_df = df[df['Loaner'].str.lower() == user_name.lower()]
                if not credits_df.empty:
                    output_path = os.path.join(
                        output_dir,
                        f"credits_{user_name}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv"
                    )
                    credits_df.to_csv(output_path, index=False)
                    window['-STATUS-'].update('Credits retrieved successfully!', text_color='green')
                    sg.popup('Success', f'Credits for {user_name} saved to output folder.')
                else:
                    window['-STATUS-'].update('No credits found.', text_color='orange')
                    sg.popup('Info', f'No credits found for {user_name}.')
            except Exception as e:
                traceback.print_exc()
                window['-STATUS-'].update('Error retrieving credits.', text_color='red')
                sg.popup_error('Error', f'Failed to retrieve credits: {e}')

        elif event == '-CHANGEUSER-':
            current_user = config['splitwise_api']['expenses']['user_name']
            new_user = sg.popup_get_text(f'Current user: {current_user}\nEnter new user name:')
            if new_user and new_user.strip():
                try:
                    config['splitwise_api']['expenses']['user_name'] = new_user.strip()
                    with open(config_file_path, 'w') as file:
                        yaml.dump(config, file, default_flow_style=False)
                    window['-USER-'].update(f'Current User: {new_user.strip()}')
                    window['-STATUS-'].update('User name updated successfully!', text_color='green')
                    sg.popup('Success', f'User name changed to: {new_user.strip()}')
                except Exception as e:
                    traceback.print_exc()
                    window['-STATUS-'].update('Error updating user name.', text_color='red')
                    sg.popup_error('Error', f'Failed to update user name: {e}')

    window.close()


if __name__ == '__main__':
    main()
