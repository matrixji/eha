"""
agent configuration helper
"""

from os import path, environ
import yaml


CONF_FILE = '/etc/eha/agent.yaml'


def load():
    """
    load configuration from system.

    1. try load configure(default section) from /etc/eha/agent.yaml
    2. update if enviroument are provided EHA_AGENT_xxx
    """
    config = dict()
    if path.isfile(CONF_FILE):
        with open(CONF_FILE, 'r') as file_handle:
            config = yaml.load(file_handle, yaml.loader.FullLoader)
    for key in environ:
        if key.startswith('EHA_AGENT_'):
            config[key[10:].lower()] = environ[key]
    return config
