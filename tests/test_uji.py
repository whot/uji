#!/usr/bin/env python3

from typing import Optional

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


def find_in_section(markdown: str, section: str, string: str) -> Optional[str]:
    prev_line = None
    in_section = False
    for line in markdown.split('\n'):
        if prev_line is not None and prev_line == section and line == '-' * len(section):
            in_section = True
        elif in_section and line == '':
            in_section = False
        elif in_section:
            if string in line:
                return line
        prev_line = line

    return None


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

        # check for the tests to be distributed across the actors
        # correctly
        assert find_in_section(markdown, 'Generic', 'testcase1')
        assert find_in_section(markdown, 'Generic', 'file01')
        assert find_in_section(markdown, 'Generic', 'file02')

        assert find_in_section(markdown, 'actor1', 'testcase3')
        assert find_in_section(markdown, 'actor2', 'testcase3')

        assert find_in_section(markdown, 'actor1', 'testcase4')
        assert find_in_section(markdown, 'actor1', 'file04')
        assert not find_in_section(markdown, 'actor2', 'testcase4')
        assert not find_in_section(markdown, 'actor2', 'file04')

        assert not find_in_section(markdown, 'actor1', 'testcase5')
        assert not find_in_section(markdown, 'actor1', 'testcase5.1')
        assert not find_in_section(markdown, 'actor1', 'testcase5.2')
        assert not find_in_section(markdown, 'actor1', 'file05')

        assert find_in_section(markdown, 'actor2', 'testcase5')
        assert find_in_section(markdown, 'actor2', 'testcase5.1')
        assert find_in_section(markdown, 'actor2', 'testcase5.2')
        assert find_in_section(markdown, 'actor2', 'file05')

        assert find_in_section(markdown, 'actor1', 'testcase6'), markdown
        assert not find_in_section(markdown, 'actor2', 'testcase6'), markdown

        assert not find_in_section(markdown, 'actor1', 'testcase7'), markdown
        assert find_in_section(markdown, 'actor2', 'testcase7'), markdown

        # Check for the 'emtpy' files to be created
        assert (Path('testdir') / 'generic' / 'test1' / 'file01-generic').exists()
        assert (Path('testdir') / 'generic' / 'test2' / 'file02-generic').exists()
        assert (Path('testdir') / 'actor1' / 'test4' / 'file04-actor-one').exists()
        assert (Path('testdir') / 'actor2' / 'test5' / 'file05-actor-two').exists()

