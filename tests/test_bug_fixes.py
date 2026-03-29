import pytest
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def make_mock_user(first_name, paid_share, owed_share):
    user = MagicMock()
    user.getFirstName.return_value = first_name
    user.getPaidShare.return_value = str(paid_share)
    user.getOwedShare.return_value = str(owed_share)
    return user


def make_mock_expense(loaner_name, borrower_name, cost,
                      loaner_paid, loaner_owed,
                      borrower_paid, borrower_owed,
                      description, date,
                      extra_users=None):
    loaner = make_mock_user(loaner_name, loaner_paid, loaner_owed)
    borrower = make_mock_user(borrower_name, borrower_paid, borrower_owed)
    users = [loaner, borrower] + (extra_users or [])
    expense = MagicMock()
    expense.getUsers.return_value = users
    expense.getCost.return_value = str(cost)
    expense.getDescription.return_value = description
    expense.getDate.return_value = date
    return expense


def make_splitwise_instance(expenses):
    from splitwise_expenses import SplitwiseExpenses
    instance = SplitwiseExpenses.__new__(SplitwiseExpenses)
    instance.expenses = expenses
    instance.update_after = None
    return instance


# ── Issue 1: Recurring expenses ──────────────────────────────────────────────

def _make_expense(expense_id, loaner, borrower, cost, description, date,
                  loaner_paid=None, loaner_owed=None, borrower_owed=None):
    loaner_paid = loaner_paid if loaner_paid is not None else cost
    loaner_owed = loaner_owed if loaner_owed is not None else cost / 2
    borrower_owed = borrower_owed if borrower_owed is not None else cost / 2
    e = make_mock_expense(loaner, borrower, cost,
                          loaner_paid, loaner_owed, 0, borrower_owed,
                          description, date)
    e.getId.return_value = str(expense_id)
    return e


def _processed(expense, ynab_ids=None):
    """Build a processed_expenses dict entry for an expense (simulates a prior sync).

    Uses the current format: {expense_id: {"hash": str, "ynab_ids": [str]}}.
    Pass ynab_ids to simulate a previous YNAB transaction being stored.
    """
    from splitwise_expenses import _expense_content_hash
    return {
        str(expense.getId()): {
            "hash": _expense_content_hash(expense),
            "ynab_ids": ynab_ids or [],
        }
    }


def _processed_legacy(expense):
    """Build a processed_expenses dict in the OLD (plain hash string) format."""
    from splitwise_expenses import _expense_content_hash
    return {str(expense.getId()): _expense_content_hash(expense)}


class TestProcessedExpensesFilter:

    def test_no_processed_expenses_returns_all(self):
        expenses = [
            _make_expense(1, "Alice", "Tulio", 20, "Dinner", "2024-03-01T00:00:00Z"),
            _make_expense(2, "Alice", "Tulio", 20, "Lunch",  "2024-03-15T00:00:00Z"),
        ]
        sw = make_splitwise_instance(expenses)
        df = sw.get_borrowed_expenses_by_user("Tulio", processed_expenses=None)
        assert len(df) == 2

    def test_known_id_with_matching_hash_is_skipped(self):
        e1 = _make_expense(1, "Alice", "Tulio", 20, "Dinner", "2024-03-01T00:00:00Z")
        e2 = _make_expense(2, "Alice", "Tulio", 20, "Lunch",  "2024-03-15T00:00:00Z")
        sw = make_splitwise_instance([e1, e2])
        df = sw.get_borrowed_expenses_by_user("Tulio", processed_expenses=_processed(e1))
        assert len(df) == 1
        assert df.iloc[0]['expense_id'] == '2'

    def test_all_known_and_unchanged_returns_empty(self):
        e1 = _make_expense(1, "Alice", "Tulio", 20, "Dinner", "2024-03-01T00:00:00Z")
        sw = make_splitwise_instance([e1])
        df = sw.get_borrowed_expenses_by_user("Tulio", processed_expenses=_processed(e1))
        assert df.empty

    def test_recurring_restamped_same_content_is_skipped(self):
        """Splitwise refreshes updated_at on old recurring expense — content unchanged → skip."""
        old = _make_expense(101, "Alice", "Tulio", 50, "Rent share", "2024-02-01T00:00:00Z")
        new = _make_expense(202, "Alice", "Tulio", 50, "Rent share", "2024-03-01T00:00:00Z")
        sw = make_splitwise_instance([old, new])
        df = sw.get_borrowed_expenses_by_user("Tulio", processed_expenses=_processed(old))
        assert len(df) == 1
        assert df.iloc[0]['expense_id'] == '202'
        assert df.iloc[0]['Date'] == "2024-03-01"

    def test_backdated_new_expense_passes_through(self):
        """Late-added expense dated in the past has a new ID → must be included."""
        synced   = _make_expense(10, "Alice", "Tulio", 20, "Dinner", "2024-03-01T00:00:00Z")
        backdated = _make_expense(11, "Alice", "Tulio", 20, "Taxi",  "2024-02-15T00:00:00Z")
        sw = make_splitwise_instance([synced, backdated])
        df = sw.get_borrowed_expenses_by_user("Tulio", processed_expenses=_processed(synced))
        assert len(df) == 1
        assert df.iloc[0]['expense_id'] == '11'
        assert df.iloc[0]['Date'] == "2024-02-15"

    def test_edited_expense_same_id_different_hash_is_resynced(self):
        """An expense edited after sync (amount changed) must be re-included."""
        original = _make_expense(42, "Alice", "Tulio", 20, "Dinner", "2024-03-01T00:00:00Z")
        edited   = _make_expense(42, "Alice", "Tulio", 30, "Dinner", "2024-03-01T00:00:00Z")
        sw = make_splitwise_instance([edited])
        # processed_expenses has the hash of the original (pre-edit) version
        df = sw.get_borrowed_expenses_by_user("Tulio", processed_expenses=_processed(original))
        assert len(df) == 1
        assert df.iloc[0]['expense_id'] == '42'
        assert df.iloc[0]['Share'] == pytest.approx(15.0)  # half of updated 30

    def test_updated_expense_id_detected_as_updated_not_new(self):
        """The main flow must distinguish updated expenses (ID already known) from new ones,
        so the hash guard only fires for new ones upfront."""
        original = _make_expense(42, "Alice", "Tulio", 20, "Dinner", "2024-03-01T00:00:00Z")
        edited   = _make_expense(42, "Alice", "Tulio", 30, "Dinner", "2024-03-01T00:00:00Z")
        new_exp  = _make_expense(99, "Alice", "Tulio", 10, "Taxi",   "2024-03-10T00:00:00Z")
        sw = make_splitwise_instance([edited, new_exp])

        stored = _processed(original)  # only original hash stored
        df = sw.get_borrowed_expenses_by_user("Tulio", processed_expenses=stored)

        updated_ids = set(df['expense_id']) & set(stored.keys())
        new_ids     = set(df['expense_id']) - set(stored.keys())

        assert updated_ids == {'42'}   # edited expense is an update, not new
        assert new_ids     == {'99'}   # taxi is genuinely new


# ── Issue 2: Multiple payers ──────────────────────────────────────────────────

class TestMultiplePayers:

    def test_single_payer_unchanged(self):
        """Baseline: single payer still produces one row with full share."""
        expense = make_mock_expense("Alice", "Tulio", 30, 30, 10, 0, 20,
                                    "Dinner", "2024-03-01T00:00:00Z")
        sw = make_splitwise_instance([expense])
        df = sw.get_borrowed_expenses_by_user("Tulio")
        assert len(df) == 1
        assert df.iloc[0]['Loaner'] == "Alice"
        assert df.iloc[0]['Share'] == 20.0

    def test_two_equal_payers_split_share_evenly(self):
        """Alice and Bob each paid half; Tulio's share should be split 50/50."""
        # Total cost: 30. Each person owes 10.
        # Alice paid 20, owes 10 → net +10
        # Bob paid 20, owes 10 → net +10
        # Tulio paid 0, owes 10 → owes 5 to Alice, 5 to Bob
        alice = make_mock_user("Alice", 20, 10)
        bob = make_mock_user("Bob", 20, 10)
        tulio = make_mock_user("Tulio", 0, 10)
        expense = MagicMock()
        expense.getUsers.return_value = [alice, bob, tulio]
        expense.getCost.return_value = "30"
        expense.getDescription.return_value = "Dinner"
        expense.getDate.return_value = "2024-03-01T00:00:00Z"

        sw = make_splitwise_instance([expense])
        df = sw.get_borrowed_expenses_by_user("Tulio")

        assert len(df) == 2
        loaners = set(df['Loaner'])
        assert loaners == {"Alice", "Bob"}
        assert df['Share'].sum() == pytest.approx(10.0)
        assert df[df['Loaner'] == 'Alice']['Share'].iloc[0] == pytest.approx(5.0)
        assert df[df['Loaner'] == 'Bob']['Share'].iloc[0] == pytest.approx(5.0)

    def test_two_unequal_payers_split_share_proportionally(self):
        """Alice paid 40, Bob paid 20, each owes 10; Tulio owes 10 total.
        Alice net = 30, Bob net = 10 → Tulio owes Alice 7.50, Bob 2.50."""
        alice = make_mock_user("Alice", 40, 10)
        bob = make_mock_user("Bob", 20, 10)
        tulio = make_mock_user("Tulio", 0, 10)
        expense = MagicMock()
        expense.getUsers.return_value = [alice, bob, tulio]
        expense.getCost.return_value = "60"
        expense.getDescription.return_value = "Trip"
        expense.getDate.return_value = "2024-03-01T00:00:00Z"

        sw = make_splitwise_instance([expense])
        df = sw.get_borrowed_expenses_by_user("Tulio")

        assert len(df) == 2
        assert df['Share'].sum() == pytest.approx(10.0)
        assert df[df['Loaner'] == 'Alice']['Share'].iloc[0] == pytest.approx(7.5)
        assert df[df['Loaner'] == 'Bob']['Share'].iloc[0] == pytest.approx(2.5)

    def test_neutral_payer_not_added_as_loaner(self):
        """Bob paid exactly his share (net 0) — should not appear as a loaner."""
        alice = make_mock_user("Alice", 30, 10)  # net +20
        bob = make_mock_user("Bob", 10, 10)       # net 0
        tulio = make_mock_user("Tulio", 0, 20)
        expense = MagicMock()
        expense.getUsers.return_value = [alice, bob, tulio]
        expense.getCost.return_value = "40"
        expense.getDescription.return_value = "Groceries"
        expense.getDate.return_value = "2024-03-01T00:00:00Z"

        sw = make_splitwise_instance([expense])
        df = sw.get_borrowed_expenses_by_user("Tulio")

        assert len(df) == 1
        assert df.iloc[0]['Loaner'] == "Alice"
        assert df.iloc[0]['Share'] == pytest.approx(20.0)


# ── Issue 3: Legacy processed_expenses format migration ──────────────────────

class TestLegacyFormatMigration:

    def test_legacy_hash_string_skips_unchanged_expense(self):
        """Old format (plain hash string) must still cause unchanged expenses to be skipped."""
        e1 = _make_expense(1, "Alice", "Tulio", 20, "Dinner", "2024-03-01T00:00:00Z")
        sw = make_splitwise_instance([e1])
        legacy = _processed_legacy(e1)
        df = sw.get_borrowed_expenses_by_user("Tulio", processed_expenses=legacy)
        assert df.empty

    def test_legacy_hash_string_passes_edited_expense(self):
        """Old format with stale hash → expense was edited → must be included."""
        original = _make_expense(1, "Alice", "Tulio", 20, "Dinner", "2024-03-01T00:00:00Z")
        edited   = _make_expense(1, "Alice", "Tulio", 30, "Dinner", "2024-03-01T00:00:00Z")
        sw = make_splitwise_instance([edited])
        legacy = _processed_legacy(original)
        df = sw.get_borrowed_expenses_by_user("Tulio", processed_expenses=legacy)
        assert len(df) == 1
        assert df.iloc[0]['Share'] == pytest.approx(15.0)

    def test_new_format_dict_skips_unchanged_expense(self):
        """New dict format {id: {"hash": ..., "ynab_ids": [...]}} skips unchanged expense."""
        e1 = _make_expense(1, "Alice", "Tulio", 20, "Dinner", "2024-03-01T00:00:00Z")
        sw = make_splitwise_instance([e1])
        stored = _processed(e1, ynab_ids=["ynab-txn-abc"])
        df = sw.get_borrowed_expenses_by_user("Tulio", processed_expenses=stored)
        assert df.empty

    def test_new_format_dict_passes_edited_expense(self):
        """New dict format with stale hash → expense was edited → must be included."""
        original = _make_expense(1, "Alice", "Tulio", 20, "Dinner", "2024-03-01T00:00:00Z")
        edited   = _make_expense(1, "Alice", "Tulio", 30, "Dinner", "2024-03-01T00:00:00Z")
        sw = make_splitwise_instance([edited])
        stored = _processed(original, ynab_ids=["ynab-txn-abc"])
        df = sw.get_borrowed_expenses_by_user("Tulio", processed_expenses=stored)
        assert len(df) == 1
        assert df.iloc[0]['Share'] == pytest.approx(15.0)


# ── Issue 4: YNAB deduplication on update ────────────────────────────────────

class TestYNABDeduplication:

    def _make_ynab(self):
        from ynab_expenses import YNABExpenses
        ynab = YNABExpenses.__new__(YNABExpenses)
        ynab.ynab_token = "fake"
        ynab.budget_id = "budget-1"
        ynab.account_id = "account-1"
        ynab.categories = []
        ynab.base_url = "https://api.youneedabudget.com/v1"
        ynab.headers = {"Authorization": "Bearer fake", "Content-Type": "application/json"}
        return ynab

    def test_add_expenses_returns_transaction_ids(self):
        """add_expenses must return the list of YNAB transaction IDs from the API response."""
        import pandas as pd
        ynab = self._make_ynab()
        row = {
            'Share': 10.0, 'Date': '2024-03-01', 'Loaner': 'Alice',
            'Description': 'Dinner', 'category_id': None
        }
        df = pd.DataFrame([row])
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            'data': {'transaction_ids': ['ynab-txn-xyz']}
        }
        with patch('requests.post', return_value=mock_response):
            ids = ynab.add_expenses(df)
        assert ids == ['ynab-txn-xyz']

    def test_delete_transactions_calls_api_for_each_id(self):
        """delete_transactions must issue one DELETE call per YNAB transaction ID."""
        ynab = self._make_ynab()
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        with patch('requests.delete', return_value=mock_response) as mock_del:
            ynab.delete_transactions(['id-1', 'id-2'])
        assert mock_del.call_count == 2
        urls = [call.args[0] for call in mock_del.call_args_list]
        assert any('id-1' in u for u in urls)
        assert any('id-2' in u for u in urls)

    def test_delete_transactions_empty_list_is_noop(self):
        """Calling delete_transactions([]) must not hit the YNAB API."""
        ynab = self._make_ynab()
        with patch('requests.delete') as mock_del:
            ynab.delete_transactions([])
        mock_del.assert_not_called()

    def _post_body(self, mock_post):
        """Return the JSON body sent to the YNAB API in the first POST call."""
        import json as _json
        call_kwargs = mock_post.call_args
        return call_kwargs.kwargs.get('json') or call_kwargs.args[1]

    def test_all_expenses_submitted_unapproved(self):
        """All expenses (new and updated) must be submitted with approved=False."""
        import pandas as pd
        ynab = self._make_ynab()
        df = pd.DataFrame([{
            'Share': 10.0, 'Date': '2024-03-01', 'Loaner': 'Alice',
            'Description': 'Dinner', 'category_id': None,
        }])
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {'data': {'transaction_ids': ['t1']}}
        with patch('requests.post', return_value=mock_response) as mock_post:
            ynab.add_expenses(df, approved=False)
        body = self._post_body(mock_post)
        assert body['transactions'][0]['approved'] is False

    def test_updated_expense_is_unapproved(self):
        """Updated expenses must be submitted with approved=False so they appear
        in YNAB's 'To Be Approved' queue."""
        import pandas as pd
        ynab = self._make_ynab()
        df = pd.DataFrame([{
            'Share': 15.0, 'Date': '2024-03-01', 'Loaner': 'Alice',
            'Description': 'Dinner', 'category_id': None,
        }])
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {'data': {'transaction_ids': ['t2']}}
        with patch('requests.post', return_value=mock_response) as mock_post:
            ynab.add_expenses(df, approved=False)
        body = self._post_body(mock_post)
        assert body['transactions'][0]['approved'] is False
