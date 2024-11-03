import yaml

def read_yaml_config(file_path):
    with open(file_path, 'r') as config_file:
        try:
            config = yaml.safe_load(config_file)
            return config
        except yaml.YAMLError as e:
            print(f"Error reading YAML file: {e}")
            return None
