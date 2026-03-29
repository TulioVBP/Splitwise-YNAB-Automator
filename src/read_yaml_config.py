import yaml

REQUIRED_CONFIG_KEYS = ['splitwise_api', 'ynab_api', 'output']

def read_yaml_config(file_path):
    try:
        with open(file_path, 'r') as config_file:
            config = yaml.safe_load(config_file)
    except FileNotFoundError:
        raise RuntimeError(f"Config file not found: {file_path}")
    except yaml.YAMLError as e:
        raise RuntimeError(f"Failed to parse config file: {e}")

    if config is None:
        raise RuntimeError(f"Config file is empty: {file_path}")

    missing = [k for k in REQUIRED_CONFIG_KEYS if k not in config]
    if missing:
        raise RuntimeError(f"Config missing required keys: {missing}")

    return config
