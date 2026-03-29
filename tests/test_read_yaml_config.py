import pytest
import sys
import os
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from read_yaml_config import read_yaml_config


VALID_CONFIG = textwrap.dedent("""\
    splitwise_api:
      consumer_key: key
      consumer_secret: secret
      api_key: apikey
    ynab_api:
      token: token
    output:
      output_dir: /tmp
""")


def test_returns_dict_for_valid_config(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text(VALID_CONFIG)
    config = read_yaml_config(str(f))
    assert isinstance(config, dict)
    assert config['splitwise_api']['consumer_key'] == 'key'


def test_raises_on_missing_file():
    with pytest.raises(RuntimeError, match="Config file not found"):
        read_yaml_config("/nonexistent/path/config.yaml")


def test_raises_on_empty_file(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text("")
    with pytest.raises(RuntimeError, match="Config file is empty"):
        read_yaml_config(str(f))


def test_raises_on_invalid_yaml(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text("key: [unclosed bracket")
    with pytest.raises(RuntimeError, match="Failed to parse config file"):
        read_yaml_config(str(f))


def test_raises_on_missing_required_key(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text("splitwise_api:\n  key: val\nynab_api:\n  token: t\n")
    with pytest.raises(RuntimeError, match="missing required keys"):
        read_yaml_config(str(f))


def test_error_message_lists_all_missing_keys(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text("unrelated_key: value\n")
    with pytest.raises(RuntimeError) as exc_info:
        read_yaml_config(str(f))
    msg = str(exc_info.value)
    assert "splitwise_api" in msg
    assert "ynab_api" in msg
    assert "output" in msg
