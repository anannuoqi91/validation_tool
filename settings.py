import json
import os
import sys
from easydict import EasyDict as edict
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'
sys.path.append('/apollo/cyber/lib/python3.8/site-packages/cyber/python')
sys.path.append(os.path.join(os.path.dirname(__file__), 'proto'))


class JsonConfig:
    def __init__(self, file_path, default_value):
        self.file_path = file_path
        self.data = default_value

        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)
                    self.data = edict(loaded_data)
                print(f"Config loaded from {file_path}")
            except (json.JSONDecodeError, IOError):
                print("Failed to load JSON file, using default value")

        self._save()

    def _save(self):
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=4)

    def update(self):
        self._save()


DEFAULT_CONFIG = edict({
    'log': {
        'log_dir': './logs',
        'log_level': 'INFO',
    },
    'port': {
        'frontend': '3000',
        'backend': '5000',
    },
    'base_dir': './temp',
})


app_settings = JsonConfig('./app_config.json', DEFAULT_CONFIG)
app_config = app_settings.data
