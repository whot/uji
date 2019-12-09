#!/usr/bin/env python3

import pytest
from uji import MarkdownParser, MarkdownError
from textwrap import dedent
from pathlib import Path


@pytest.fixture
def datadir():
    import os
    return Path(os.path.realpath(__file__)).parent / 'data'


def check_is_paragraph(node, text):
    assert isinstance(node, MarkdownParser.Paragraph)
    assert text in node.text


def check_is_section(node, text, level):
    assert isinstance(node, MarkdownParser.Section)
    assert node.headline.startswith(text)
    assert node.level == level


def check_is_checkbox(node, text):
    assert isinstance(node, MarkdownParser.Checkbox)
    assert text in node.text


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
    root = md.tree
    assert len(root.children) == 2
    h2 = root.children[0]
    check_is_section(h2, 'h2', level=2)
    h3 = h2.children[1]
    check_is_section(h3, 'h3', level=3)
    h1 = root.children[1]
    check_is_section(h1, 'h1', level=1)


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
    root = md.tree
    assert len(root.children) == 2

    h1 = root.children[0]
    check_is_section(h1, 'h1', level=1)
    for i in range(5):
        assert md.lines[i].section == h1

    h2 = h1.children[1]
    check_is_section(h2, 'h2', level=2)
    for i in range(5, 8):
        assert md.lines[i].section == h2

    h2 = h1.children[2]
    check_is_section(h2, 'h2', level=2)
    for i in range(8, 11):
        assert md.lines[i].section == h2

    h1 = root.children[1]
    check_is_section(h1, 'h1', level=1)

    data = dedent('''\
                  foo
                  ===
                  bar
                  ---
                  baz
                  ---
                  ''')
    md = MarkdownParser.from_text(data)
    assert len(md.tree.children) == 1

def test_mdfile_complex(datadir):
    md = MarkdownParser.from_file(datadir / 'parsertest.md')
    root = md.tree

    assert len(root.children) == 5

    check_is_paragraph(root.children[0], 'ONE')
    check_is_checkbox(root.children[1], 'TWO')
    check_is_checkbox(root.children[1], 'TWO')
    cb = root.children[2]
    check_is_paragraph(cb.children[0], 'FOUR')

    h1 = root.children[3]
    check_is_section(h1, 'FIVE', level=1)

    check_is_paragraph(h1.children[0], 'SIX')

    cb = h1.children[1]
    check_is_checkbox(cb, 'SEVEN')
    check_is_paragraph(cb.children[0], 'EIGHT')

    cb = h1.children[2]
    check_is_checkbox(cb, 'NINE')

    h2 = h1.children[3]
    check_is_section(h2, 'TEN', level=2)
    check_is_paragraph(h2.children[0], 'ELEVEN')
    check_is_paragraph(h2.children[0], 'TWELVE')
    check_is_checkbox(h2.children[1], 'THIRTEEN')
    check_is_checkbox(h2.children[2], 'FOURTEEN')
    check_is_paragraph(h2.children[3], 'FIFTEEN')

    h2 = h1.children[4]
    check_is_section(h2, 'SIXTEEN', level=2)
    check_is_paragraph(h2.children[0], 'SEVENTEEN')
    check_is_checkbox(h2.children[1], 'EIGHTEEN')

    h3 = h2.children[2]
    check_is_section(h3, 'NINETEEN', level=3)
    check_is_checkbox(h3.children[0], 'TWENTY')

    h3 = h2.children[3]
    check_is_section(h3, 'TWENTYONE', level=3)
    check_is_paragraph(h3.children[0], 'TWENTYTWO')
    check_is_checkbox(h3.children[1], 'TWENTYTHREE')

    h1 = root.children[4]
    check_is_section(h1, 'TWENTYFOUR', level=1)
    assert len(h1.children) == 1
    check_is_paragraph(h1.children[0], 'TWENTYFIVE')
    check_is_paragraph(h1.children[0], 'TWENTYSIX')
    check_is_paragraph(h1.children[0], 'TWENTYSEVEN')
