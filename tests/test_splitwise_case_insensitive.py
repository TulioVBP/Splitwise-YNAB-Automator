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


def make_mock_expense(loaner_name, borrower_name, cost, loaner_share, borrower_share, description, date):
    loaner = make_mock_user(loaner_name, loaner_share, 0.0)
    borrower = make_mock_user(borrower_name, 0.0, borrower_share)
    expense = MagicMock()
    expense.getUsers.return_value = [loaner, borrower]
    expense.getCost.return_value = str(cost)
    expense.getDescription.return_value = description
    expense.getDate.return_value = date
    return expense


def make_splitwise_instance(expenses):
    """Build a SplitwiseExpenses instance without hitting the real API."""
    with patch('splitwise_expenses.Splitwise') as MockSplitwise:
        mock_sw = MagicMock()
        mock_sw.getExpenses.return_value = expenses
        MockSplitwise.return_value = mock_sw

        from splitwise_expenses import SplitwiseExpenses
        config = {
            'splitwise_api': {
                'consumer_key': 'k',
                'consumer_secret': 's',
                'api_key': 'a',
                'expenses': {'from_date': MagicMock(isoformat=lambda: '2024-01-01')},
            }
        }
        instance = SplitwiseExpenses.__new__(SplitwiseExpenses)
        instance.expenses = expenses
        instance.update_after = None
        return instance


class TestCaseInsensitiveUserMatching:

    def test_exact_case_match_finds_expense(self):
        expense = make_mock_expense("Alice", "Tulio", 20.0, 20.0, 10.0, "Dinner", "2024-03-01T00:00:00")
        sw = make_splitwise_instance([expense])
        df = sw.get_borrowed_expenses_by_user("Tulio")
        assert not df.empty
        assert df.iloc[0]['Share'] == 10.0

    def test_lowercase_query_matches_titlecase_api_name(self):
        expense = make_mock_expense("Alice", "Tulio", 20.0, 20.0, 10.0, "Dinner", "2024-03-01T00:00:00")
        sw = make_splitwise_instance([expense])
        df = sw.get_borrowed_expenses_by_user("tulio")
        assert not df.empty

    def test_uppercase_query_matches_titlecase_api_name(self):
        expense = make_mock_expense("Alice", "Tulio", 20.0, 20.0, 10.0, "Dinner", "2024-03-01T00:00:00")
        sw = make_splitwise_instance([expense])
        df = sw.get_borrowed_expenses_by_user("TULIO")
        assert not df.empty

    def test_user_is_loaner_skipped_regardless_of_case(self):
        # Tulio paid — should be excluded even if query uses different case
        expense = make_mock_expense("Tulio", "Alice", 20.0, 20.0, 10.0, "Dinner", "2024-03-01T00:00:00")
        sw = make_splitwise_instance([expense])
        df = sw.get_borrowed_expenses_by_user("tulio")
        assert df.empty

    def test_payment_description_always_skipped(self):
        expense = make_mock_expense("Alice", "Tulio", 20.0, 20.0, 10.0, "Payment", "2024-03-01T00:00:00")
        sw = make_splitwise_instance([expense])
        df = sw.get_borrowed_expenses_by_user("Tulio")
        assert df.empty

    def test_unrelated_user_not_included(self):
        expense = make_mock_expense("Alice", "Bob", 20.0, 20.0, 10.0, "Lunch", "2024-03-01T00:00:00")
        sw = make_splitwise_instance([expense])
        df = sw.get_borrowed_expenses_by_user("Tulio")
        assert df.empty

    def test_multiple_expenses_mixed_cases(self):
        expenses = [
            make_mock_expense("Alice", "Tulio", 30.0, 30.0, 15.0, "Dinner", "2024-03-01T00:00:00"),
            make_mock_expense("Bob", "TULIO", 40.0, 40.0, 20.0, "Taxi", "2024-03-02T00:00:00"),
        ]
        sw = make_splitwise_instance(expenses)
        df = sw.get_borrowed_expenses_by_user("Tulio")
        assert len(df) == 2
        assert df['Share'].sum() == 35.0
