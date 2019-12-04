#!/usr/bin/env python3

from click.testing import CliRunner
import pytest
import os
import git
import uji
from pathlib import Path


@pytest.fixture
def datadir():
    import os
    return Path(os.path.realpath(__file__)).parent / 'data'


def test_uji_example(datadir):
    args = ['new', os.fspath(Path(datadir) / 'example.yaml')]
    runner = CliRunner()
    with runner.isolated_filesystem():
        git.Repo.init('.')
        result = runner.invoke(uji.uji, args)
        assert result.exit_code == 0
