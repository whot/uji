#!/usr/bin/env python3

import pytest
import os
from uji import Uji
from textwrap import dedent
from pathlib import Path

@pytest.fixture
def datadir():
    import os
    return Path(os.path.realpath(__file__)).parent / 'data'


def test_uji_example(datadir):
    Uji().run(['new', os.fspath(Path(datadir) / 'example.yaml')])

