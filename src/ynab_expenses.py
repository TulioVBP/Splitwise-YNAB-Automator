import re
import requests

_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}')

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

    def get_categories(self):
        """
        Fetch all active categories from the YNAB budget.
        Returns a list of dicts: [{'name': 'Group / Category', 'category_id': '...'}, ...]
        Hidden and deleted categories are excluded.
        """
        url = f"{self.base_url}/budgets/{self.budget_id}/categories"
        response = requests.get(url, headers=self.headers)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            print("YNAB API error:", response.text)
            raise

        categories = []
        for group in response.json()['data']['category_groups']:
            if group.get('hidden') or group.get('deleted'):
                continue
            for cat in group['categories']:
                if cat.get('hidden') or cat.get('deleted'):
                    continue
                categories.append({
                    'name': f"{group['name']} / {cat['name']}",
                    'category_id': cat['id'],
                })
        return categories

    def add_expenses(self, expenses_df, approved: bool = True) -> list:
        """
        Add new Splitwise expenses to YNAB as transactions.
        Args:
            expenses_df (pd.DataFrame): DataFrame with columns: Date, Amount, Description
            approved (bool): Whether to mark the transaction as approved in YNAB.
                             Pass False for updated expenses so they appear in the
                             "To Be Approved" queue for manual review.
        Returns:
            list[str]: YNAB transaction IDs that were created
        """
        if expenses_df.empty:
            print("No expenses to submit to YNAB.")
            return []

        url = f"{self.base_url}/budgets/{self.budget_id}/transactions"
        headers = self.headers
        transactions = []
        for _, row in expenses_df.iterrows():
            amount = round(float(row['Share']) * 1000)
            date_raw = str(row['Date'])
            if not _DATE_RE.match(date_raw):
                raise ValueError(f"Unexpected date format in expense row: {date_raw!r}")
            parent_transaction = {
                "account_id": self.account_id,
                "date": date_raw[:10],
                "amount": 0,
                "payee_name": row.get('Loaner', ''),
                "memo": row.get('Description', ''),
                "cleared": "cleared",
                "approved": approved,
                "subtransactions": [
                    {
                        "amount": -amount,
                        "category_id": row.get('category_id') or None,
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
        except requests.exceptions.HTTPError:
            print("YNAB API error:", response.text)
            raise
        return response.json().get('data', {}).get('transaction_ids', [])

    def delete_transaction(self, ynab_transaction_id: str) -> None:
        """Delete a single YNAB transaction by its ID."""
        url = f"{self.base_url}/budgets/{self.budget_id}/transactions/{ynab_transaction_id}"
        response = requests.delete(url, headers=self.headers)
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            print("YNAB API error:", response.text)
            raise

    def delete_transactions(self, ynab_ids: list) -> None:
        """Delete multiple YNAB transactions by their IDs."""
        for tid in ynab_ids:
            self.delete_transaction(tid)
