"""
testing for agent's config
"""

import os
import pytest
import yaml
from eha.agent.config import load


@pytest.mark.parametrize('content, envs, result', (
    (
        """
foo: 123
bar: 234
        """,
        {},
        {
            'foo': 123,
            'bar': 234,
        }
    ),
    (
        """
foo: 123
bar: 234
        """,
        {
            'EHA_AGENT_FOO': 'abc',
            'EHA_AGENT_BAR': '234',
        },
        {
            'foo': 'abc',
            'bar': '234',
        }
    ),
))
def test_load(content, envs, result, mocker, monkeypatch):
    patched_open = mocker.mock_open(read_data=content)
    mocker.patch('builtins.open', patched_open)
    mocker.patch('os.path.isfile', bool)
    with monkeypatch.context() as patch:
        for key, value in envs.items():
            patch.setenv(key, value)
        config = load()
        assert config == result
