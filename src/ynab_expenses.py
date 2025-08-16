import requests
import os

def add_expenses_to_ynab(ynab_token, budget_id, account_id, categories, expenses_df):
    """
    Add new Splitwise expenses to YNAB as transactions.
    Args:
        ynab_token (str): YNAB Personal Access Token
        budget_id (str): YNAB Budget ID
        account_id (str): YNAB Account ID to add transactions to
        expenses_df (pd.DataFrame): DataFrame with columns: Date, Amount, Description
    Returns:
        response (dict): YNAB API response
    """
    url = f"https://api.youneedabudget.com/v1/budgets/{budget_id}/transactions"
    headers = {
        "Authorization": f"Bearer {ynab_token}",
        "Content-Type": "application/json"
    }
    transactions = []
    for _, row in expenses_df.iterrows():
        # YNAB expects milliunits (e.g., 10.00 EUR = 10000)
        amount = int(float(row['Amount']) * 1000)
        # Parent transaction of amount 0 with two subtransactions
        parent_transaction = {
            "account_id": account_id,
            "date": str(row['Date'])[:10],
            "amount": 0,
            "payee_name": row.get('Loaner', ''),
            "memo": row.get('Description', ''),
            "cleared": "cleared",
            "approved": True,
            "subtransactions": [
                {
                    "amount": -amount,
                    "memo": f"Splitwise outflow: {row.get('Description', '')}"
                },
                {
                    "amount": amount,
                    "payee_name": row.get('Loaner', ''),
                    "category_id": categories[0]['category_id'] if categories else None,
                    "memo": f"Splitwise inflow: {row.get('Description', '')}"
                }
            ]
        }
        transactions.append(parent_transaction)
    data = {"transactions": transactions}
    response = requests.post(url, headers=headers, json=data)
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print("YNAB API error:", response.text)
        raise
    return response.json()
