import requests

class YNABExpenses:
    """
    Class to handle adding Splitwise expenses to YNAB.
    """
    def __init__(self, ynab_token, budget_id, account_id, categories=None):
        self.ynab_token = ynab_token
        self.budget_id = budget_id
        self.account_id = account_id
        self.categories = categories or []
        self.base_url = "https://api.youneedabudget.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.ynab_token}",
            "Content-Type": "application/json"
        }

    def add_expenses(self, expenses_df):
        """
        Add new Splitwise expenses to YNAB as transactions.
        Args:
            expenses_df (pd.DataFrame): DataFrame with columns: Date, Amount, Description
        Returns:
            response (dict): YNAB API response
        """
        url = f"{self.base_url}/budgets/{self.budget_id}/transactions"
        headers = self.headers
        transactions = []
        for _, row in expenses_df.iterrows():
            amount = int(float(row['Share']) * 1000)
            parent_transaction = {
                "account_id": self.account_id,
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
                        "category_id": self.categories[0]['category_id'] if self.categories else None,
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
