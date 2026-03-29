import pytest
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from get_latest_timestamp_for_user import get_latest_timestamp_for_user


def make_file(directory, name):
    path = os.path.join(directory, name)
    open(path, 'w').close()
    return path


def test_returns_latest_file_for_user(tmp_path):
    make_file(tmp_path, "borrowed_expenses_John_20240101_0900.csv")
    make_file(tmp_path, "borrowed_expenses_John_20240215_1430.csv")
    file, ts = get_latest_timestamp_for_user(str(tmp_path), "John")
    assert file == "borrowed_expenses_John_20240215_1430.csv"
    assert ts == datetime(2024, 2, 15, 14, 30)


def test_returns_none_for_nonexistent_directory():
    file, ts = get_latest_timestamp_for_user("/nonexistent/dir", "John")
    assert file is None
    assert ts is None


def test_returns_none_when_no_files_match(tmp_path):
    make_file(tmp_path, "borrowed_expenses_Jane_20240101_0900.csv")
    file, ts = get_latest_timestamp_for_user(str(tmp_path), "John")
    assert file is None
    assert ts is None


def test_returns_none_for_empty_directory(tmp_path):
    file, ts = get_latest_timestamp_for_user(str(tmp_path), "John")
    assert file is None
    assert ts is None


def test_regex_safe_with_dot_in_username(tmp_path):
    # "John.Doe" contains a dot — without re.escape this would match "JohnXDoe" too
    make_file(tmp_path, "borrowed_expenses_JohnXDoe_20240101_0900.csv")
    file, ts = get_latest_timestamp_for_user(str(tmp_path), "John.Doe")
    assert file is None
    assert ts is None


def test_regex_safe_dot_matches_correct_file(tmp_path):
    make_file(tmp_path, "borrowed_expenses_John.Doe_20240301_1000.csv")
    file, ts = get_latest_timestamp_for_user(str(tmp_path), "John.Doe")
    assert file == "borrowed_expenses_John.Doe_20240301_1000.csv"
    assert ts == datetime(2024, 3, 1, 10, 0)


def test_ignores_files_for_other_users(tmp_path):
    make_file(tmp_path, "borrowed_expenses_Alice_20240101_0900.csv")
    make_file(tmp_path, "borrowed_expenses_Bob_20240601_1200.csv")
    file, ts = get_latest_timestamp_for_user(str(tmp_path), "Alice")
    assert file == "borrowed_expenses_Alice_20240101_0900.csv"
