#!/usr/bin/env python3

from click.testing import CliRunner
import pytest
import os
import re
import git
import uji
import yaml
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

def test_uji_tree(datadir):
    args = ['new', os.fspath(Path(datadir) / 'basic-tree.yaml'), 'testdir']
    runner = CliRunner()
    with runner.isolated_filesystem():
        git.Repo.init('.')
        result = runner.invoke(uji.uji, args)
        assert result.exit_code == 0

        yml = Path('testdir') / 'basic-tree.yaml'
        assert yml.exists()
        # input and output files are expected to be the same
        with open(yml) as dest:
            with open(Path(datadir) / 'basic-tree.yaml') as source:
                assert yaml.safe_load(source) == yaml.safe_load(dest)

        md = Path('testdir') / 'basic-tree.md'
        assert md.exists()
        markdown = ''.join(open(md))

        # check for a few expected sections
        assert 'Uji\n===\n' in markdown
        assert 'actor1\n------\n' in markdown
        assert 'actor2\n------\n' in markdown
        assert 'Generic\n-------\n' in markdown

        # FIXME: check for the tests to be distributed across the actors
        # correctly

        # Check for the 'emtpy' files to be created
        assert (Path('testdir') / 'generic' / 'test1' / 'file1').exists()
        assert (Path('testdir') / 'generic' / 'test2' / 'file2').exists()
        assert (Path('testdir') / 'actor1' / 'test4' / 'file3').exists()
        assert (Path('testdir') / 'actor2' / 'test5' / 'file4').exists()

