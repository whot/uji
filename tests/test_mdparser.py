#!/usr/bin/env python3

import pytest
from uji import MarkdownParser, MarkdownError
from textwrap import dedent
from pathlib import Path


@pytest.fixture
def datadir():
    import os
    return Path(os.path.realpath(__file__)).parent / 'data'


def test_md_empty():
    with pytest.raises(MarkdownError):
        MarkdownParser.from_text('')
        assert 'Empty markdown file' in e.message


def test_md_load():
    md = MarkdownParser.from_text('foo')
    assert md is not None


def test_md_sections_hash():
    data = dedent('''\
                  ## h2

                  foo

                  ### h3

                  # h1

                  bar
                  ''')
    md = MarkdownParser.from_text(data)
    assert len(md.tree.sections) == 2
    assert md.tree.sections[0].level == 2
    assert md.tree.sections[1].level == 1


def test_md_sections_underline():
    data = dedent('''\
                  h1
                  -----

                  foo

                  h2
                  ===

                  h2-2
                  ===

                  h1
                  ----

                  bar
                  ''')
    md = MarkdownParser.from_text(data)
    assert len(md.tree.sections) == 2
    assert md.tree.sections[0].level == 1
    assert md.tree.sections[0].children[0].level == 2
    assert md.tree.sections[0].children[1].level == 2
    assert md.tree.sections[0].children[1].text == 'h2-2'
    assert md.tree.sections[1].level == 1
    assert md.tree.sections[1].children == []
    assert md.tree.sections[1].text == 'h1'

    for i in range(5):
        assert md.lines[i].section == md.tree.sections[0]
    for i in range(5, 8):
        assert md.lines[i].section == md.tree.sections[0].children[0]
    for i in range(8, 11):
        assert md.lines[i].section == md.tree.sections[0].children[1]

    data = dedent('''\
                  foo
                  ===
                  bar
                  ---
                  baz
                  ---
                  ''')
    md = MarkdownParser.from_text(data)
    assert len(md.tree.sections) == 1
