#!/usr/bin/env python3

import pytest
from uji import ExtendedYaml, YamlError
from textwrap import dedent
from pathlib import Path

@pytest.fixture
def datadir():
    import os
    return Path(os.path.realpath(__file__)).parent / 'data'


def test_yaml_load():
    yml = ExtendedYaml.load_from_stream('foo: bar')
    assert yml is not None


def test_yaml_load_invalid():
    with pytest.raises(YamlError):
        ExtendedYaml.load_from_stream('1')

    with pytest.raises(YamlError):
        ExtendedYaml.load_from_stream('[1, 2]')

    with pytest.raises(YamlError):
        ExtendedYaml.load_from_stream('[1, 2]')

    with pytest.raises(YamlError):
        ExtendedYaml.load_from_stream('foo')


def test_key_access():
    yml = ExtendedYaml.load_from_stream('foo: bar\nbaz: bat')
    assert yml['foo'] == 'bar'
    assert yml['baz'] == 'bat'

    yml = ExtendedYaml.load_from_stream('foo: [1, 2]\nbaz: bat')
    assert yml['foo'] == [1, 2]
    assert yml['baz'] == 'bat'

    yml = ExtendedYaml.load_from_stream('foo: [1, 2]\nbaz: 3')
    assert yml['foo'] == [1, 2]
    assert yml['baz'] == 3


def test_iteration():
    data = dedent('''\
                  foo: bar
                  baz: bat
                  ''')
    yml = ExtendedYaml.load_from_stream(data)
    assert [k for k in yml] == ['foo', 'baz']
    assert [(k, v) for (k, v) in yml.items()] == [('foo', 'bar'), ('baz', 'bat')]


def test_extends():
    data = dedent('''\
                  foo:
                    one: two
                  bar:
                    extends: foo
                  ''')
    yml = ExtendedYaml.load_from_stream(data)
    assert yml['foo']['one'] == 'two'
    assert yml['bar']['one'] == 'two'

    data = dedent('''\
                  foo:
                    one: two
                  bar:
                    extends: foo
                    one: three
                  ''')
    yml = ExtendedYaml.load_from_stream(data)
    assert yml['foo']['one'] == 'two'
    assert yml['bar']['one'] == 'three'

    data = dedent('''\
                  foo:
                    one: [1, 2]
                  bar:
                    extends: foo
                    one: [3, 4]
                  ''')
    yml = ExtendedYaml.load_from_stream(data)
    assert yml['foo']['one'] == [1, 2]
    assert yml['bar']['one'] == [1, 2, 3, 4]


def test_extends_invalid():
    data = dedent('''\
                  foo:
                    one: [1, 2]
                  extends: bar
                  ''')
    with pytest.raises(YamlError) as e:
        ExtendedYaml.load_from_stream(data)
        assert 'Invalid section name' in e.message

    data = dedent('''\
                  foo:
                    one: [1, 2]
                  bar:
                    extends: foobar
                  ''')
    with pytest.raises(YamlError) as e:
        ExtendedYaml.load_from_stream(data)
        assert 'Invalid section' in e.message

    data = dedent('''\
                  foo:
                    one: [1, 2]
                  bar:
                    extends: bar
                    one: str
                  ''')
    with pytest.raises(YamlError) as e:
        ExtendedYaml.load_from_stream(data)
        assert 'Mismatched' in e.message


def test_include(datadir):
    yml = ExtendedYaml.load_from_file(Path(datadir, 'include-test.yml'))
    assert yml['foo']['bar'] == 'baz'
    assert yml['one']['two'] == 'three'


def test_infinite_include(datadir):
    yml = ExtendedYaml.load_from_file(Path(datadir, 'infinite-include.yml'))
    assert yml['foo']['bar'] == 'infinite'

def test_version(datadir):
    data = dedent('''\
                  foo:
                    one: [1, 2]
                  ''')
    yml = ExtendedYaml.load_from_stream(data)
    with pytest.raises(AttributeError):
        yml.version 

    data = dedent('''\
                  version: 1
                  foo:
                    one: [1, 2]
                  ''')
    yml = ExtendedYaml.load_from_stream(data)
    assert yml.version == 1

    with pytest.raises(YamlError) as e:
        ExtendedYaml.load_from_file(Path(datadir, 'wrong-version.yml'))
        assert 'version mismatch' in e.message
