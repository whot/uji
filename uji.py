#!/bin/env python3
# vim: set expandtab shiftwidth=4:
# -*- Mode: python; coding: utf-8; indent-tabs-mode: nil -*- */
# -*- coding: utf-8 -*-
#
# Copyright (c) 2019 Red Hat, Inc.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from typing import Dict, List

import blessed
import click
import collections
import enum
import git
import io
import logging
import os
import re
import rich
import rich.console
import rich.logging
import rich.theme
import signal
import stat
import subprocess
import sys
import time
import yaml
from copy import deepcopy
from pathlib import Path
from textwrap import dedent

# Stylesheet for uji view
style = '''
[styles]
header = bold on cyan
filename = underline blue
inline = red
checkbox = green
code = on yellow
statusline = bold
statusline_inactive = gray50
statusline_active = black

info = dim cyan
warning = magenta
danger = bold red
error = red
'''

theme = rich.theme.Theme.from_file(io.StringIO(style))
logger = logging.getLogger('uji')
logger.addHandler(rich.logging.RichHandler())
logger.setLevel(logging.ERROR)


class YamlError(Exception):
    pass


class ExtendedYaml(collections.UserDict):
    '''
    A version of YAML that supports extra keywords.

    Requirements
    ============

    An extended YAML file must be a dictionary.


    Features
    ========

    extends:
    --------

    Supported in: top-level dictionaries

    The ``extends:`` keyword makes the current dictionary inherit all
    members of the extended dictionary, according to the following rules::

    - where the value is a non-empty dict, the base and new dicts are merged
    - where the value is a non-empty list, the base and new list are
      concatinated
    - where the value is an empty dict or empty list, the new value is the
      empty dict/list.
    - otherwise, the new value overwrites the base value.

    Example::

        foo:
          bar: [1, 2]
          baz:
            a: 'a'
            b: 'b'
          bat: 'foobar'

        subfoo:
          extends: bar
          bar: [3, 4]
          baz:
            c: 'c'
          bat: 'subfoobar'

    Results in the effective values for subfoo::

      subfoo:
         bar: [1, 2, 3, 4]
         baz: {a: 'a', b: 'b', c: 'c'}
         bat: 'subfoobar'
      foo:
        bar: 1

    include:
    --------

    Supported in: top-level only

    The ``include:`` keyword includes the specified file at the place. The
    path to the included file is relative to the source file.

    Example::


         # content of firstfile
         foo:
             bar: [1, 2]

         #content of secondfile
         bar:
             baz: [3, 4]

         include: firstfile

         foobar:
           extends: foo

    Not that the included file will work with the normal YAML rules,
    specifically: where the included file has a key with the same name this
    section will be overwritten with the later-defined. The position of the
    ``include`` statement thus matters a lot.

    version:
    --------

    The YAML file version (optional). Handled as attribute on this object and does not
    show up in the dictionary otherwise. This version must be a top-level
    entry in the YAML file in the form "version: 1" or whatever integer
    number and is exposed as the "version" attribute.

    Where other files are included, the version of that file must be
    identical to the first version found in any file.


    :: attribute: version

        An optional attribute with the version number as specified in the
        YAML file(s).

    '''

    def __init__(self, include_path=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.include_path = include_path

    def __load(self, stream):
        data = io.StringIO()
        self.__process_includes(stream, dest=data)
        data = yaml.safe_load(data.getvalue())
        if not isinstance(data, dict):
            raise YamlError('Invalid YAML data format, expected a dictionary')

        if data.get('extends'):
            raise YamlError('Invalid section name "extends", this is a reserved keyword')

        data = self.__process_extends(data)
        for k, v in data.items():
            self[k] = v

    def __process_includes(self, source, dest, level=0):
        '''
        Handles include: statements. Reads the source line-by-line
        and write it to the destination. Where a ``include: filename`` line
        is present, the filename is opened and this function is called
        recursively for that file.
        '''
        if level > 10:  # 10 levels of includes must be enough.
            return ''

        for line in source:
            # version check - all included files must have the same version
            # as the original file
            if line.startswith('version:'):
                version = int(line[len('version:'):].strip())
                try:
                    if self.version != version:
                        raise YamlError(f'Cannot include file {source}, version mismatch')
                except AttributeError:
                    self.version = version
                continue

            if not line.startswith('include: '):
                dest.write(line)
                continue

            # used for test cases only, really. all uji user cases use a
            # file anyway, not a string.
            if not self.include_path:
                raise YamlError('Cannot include from a text stream')

            filename = line[len('include:'):].strip()
            with open(Path(self.include_path) / filename) as included:
                self.__process_includes(included, dest, level + 1)

    def __process_extends(self, yaml):
        def merge(a, b):
            '''
            Helper function to a and b together:
            - Where a and b are lists, the result is a + b
            - Where a and b are dicts, the result is the union of a and b
            - Otherwise, the result is b

            This performs a deep copy of all lists/dicts so the result does what
            you'd expect.
            '''
            if type(a) != type(b):
                raise ValueError()

            if isinstance(a, list):
                return a + b
            elif isinstance(a, dict):
                merged = {}
                for k, v in a.items():
                    merged[k] = v
                for k, v in b.items():
                    merged[k] = v
                return merged
            else:
                return b

        # yaml is modified in the loop, so we have to list() it
        for section, data in list(yaml.items()):
            if not isinstance(data, dict):
                continue

            referenced = data.get('extends')
            if not referenced:
                continue

            if referenced not in yaml or referenced == section:
                raise YamlError(f'Invalid section for "extends: {referenced}"')

            # We need deep copies to avoid references to lists within dicts,
            # etc.
            combined = deepcopy(yaml[referenced])
            data = deepcopy(data)
            for item, value in data.items():
                if item == 'extends':
                    continue

                try:
                    base = combined[item]
                except KeyError:
                    # base doesn't have this key, so we can just
                    # write it out
                    combined[item] = value
                else:
                    try:
                        combined[item] = merge(base, value)
                    except ValueError:
                        raise YamlError(f'Mismatched types for {item} in {section} vs {referenced}')

            yaml[section] = combined

        return yaml

    @classmethod
    def load_from_file(cls, filename):
        from pathlib import Path
        path = Path(filename)
        if not path.is_file():
            raise YamlError(f'"{filename}" is not a file')

        with open(path) as f:
            yml = ExtendedYaml(include_path=Path(filename).parent)
            yml.__load(f)
            return yml

    @classmethod
    def load_from_stream(cls, stream):
        yml = ExtendedYaml()
        yml.__load(io.StringIO(stream))
        return yml


class MarkdownFormatter(object):
    '''
    A formatter object to produce GitLab-compatible markdown.
    The API is HTML-like, HTML tags are produced directly in the output,
    functions prefixed with ``as`` merely return the respective markup.

    Usage
    =====

    ::

        fmt = MarkdownFormatter(open('filename', 'w'))
        fmt.h1('This is a headline')
        fmt.p('A paragraph')
        fmt.p(f'A paragraph with {fmt.as_code("embedded code")}')

        with fmt.checkbox_list() as cb:
            cb.checkbox('first checkbox')
            cb.checkbox('second checkbox')
    '''
    def __init__(self, fd):
        self.fd = fd

    def fprint(self, text):
        print(text, file=self.fd)

    def h1(self, text):
        self.fprint(f'# {text}\n')

    def h2(self, text):
        self.fprint(f'## {text}\n')

    def h3(self, text):
        self.fprint(text)
        self.fprint('.' * len(text))

    def hr(self):
        self.fprint('---')

    def p(self, text):
        self.fprint('')
        self.fprint(text)
        self.fprint('')

    def as_code(self, text):
        return f'`{text}`'

    class _Checkboxer(object):
        def __init__(self, parent):
            self.parent = parent

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.parent.fprint('')
            return False

        def _checkbox(self, text, indent=0, symbol=''):
            spaces = " " * indent * 2
            self.parent.fprint(f'{spaces} - [ ]{" " if symbol else ""}{symbol} {text}')

        def checkbox(self, text, indent=0):
            self._checkbox(text, indent)

        def checkbox_attachment(self, text, indent=0):
            self._checkbox(text, indent, symbol='📎')

        def checkbox_command(self, text, indent=0):
            self._checkbox(text, indent, symbol='⚙')

        def file_attachment(self, filename, path):
            self.checkbox_attachment(f'[`{filename}`]({path})')

        def command_output(self, command, description, output_type, filename=None):
            if output_type == 'exitcode':
                self.checkbox_command(f'`{command}`')
                if description:
                    self.parent.fprint(f'  - {description}')
                self.checkbox(f'SUCCESS', indent=1)
                self.checkbox(f'FAIL', indent=1)
            elif output_type == 'single':
                self.checkbox_command(f'`{command}`: `COMMAND OUTPUT`')
                if description:
                    self.parent.fprint(f'  - {description}')
            elif output_type == 'multi':
                self.checkbox_command(f'`{command}`:')
                if description:
                    self.parent.fprint(f'  - {description}')
                self.parent.fprint(f'```')
                self.parent.fprint(f'   COMMAND OUTPUT')
                self.parent.fprint(f'')
                self.parent.fprint(f'```')
            elif output_type == 'attach':
                self.checkbox_command(f'[`{command}`]({filename})')
                if description:
                    self.parent.fprint(f'  - {description}')
            elif output_type == 'human':
                self.checkbox_command(f'`{command}`: **ADD COMMENTS HERE**')
                if description:
                    self.parent.fprint(f'  - {description}')

    def checkbox_list(self):
        return self._Checkboxer(self)


class UjiNew(object):
    class Actor(object):
        def __init__(self, id, yaml):
            self.id = id
            self.name = yaml.get('name', None) or self.id.replace('_', '-')
            self.description = yaml.get('description', None)
            self.tags = {}
            for tname, tvalue in yaml.get('tags', {}).items():
                self.tags[tname] = tvalue
            self.tests = []

        @classmethod
        def default_actor(cls):
            actor = {'name': 'Generic'}
            return UjiNew.Actor('generic', actor)

        def __str__(self):
            return f'UjiNew.Actor: {self.id} - {self.name}: tags {self.tags}'

    class Test(object):
        def __init__(self, id, yaml):
            self.id = id
            self.name = yaml.get('name', None)
            self.description = yaml.get('description', None)
            self.filters = {}
            for fname, fvalue in yaml.get('filter', {}).items():
                self.filters[fname] = fvalue
            self.tests = yaml.get('tests', [])
            logs = yaml.get('logs', {})
            self.files = [UjiNew.FileName(f) for f in logs.get('files', [])]
            self.commands = [UjiNew.Command(yaml) for yaml in logs.get('commands', [])]
            self.actor = None

        def __str__(self):
            return f'UjiNew.Test: {self.id}: filters {self.filters}'

    class FileName(object):
        def __init__(self, filename):
            self.filename = filename
            self.path = None

        def make_path_name(self, test, base_directory):
            directory = Path(base_directory) / test.actor.id / test.id
            directory.mkdir(parents=True, exist_ok=True)
            # Unicode Character 'DIVISION SLASH' (U+2215)
            filename = f'{self.filename}'.replace('/', '∕')
            self.path = directory / filename

        def __str__(self):
            return self.filename

    class Command(object):
        def __init__(self, yaml):
            self.run = yaml.get('run', None)
            self.description = yaml.get('description', None)
            self.output = yaml.get('output', 'single')
            self.path = None  # For the attachment where applicable

        def make_path_name(self, test, directory):
            if self.output != 'attach':
                return

            directory = Path(directory) / test.actor.id / test.id
            directory.mkdir(parents=True, exist_ok=True)

            # Unicode Character 'NO-BREAK SPACE' (U+00A0)
            # Unicode Character 'MINUS SIGN' (U+2212)
            run = self.run.replace(' ', '\u00A0').replace('-', '\u2212')
            self.path = Path(directory) / run

    def __init__(self, filename, target_directory):
        assert filename

        self.filename = Path(filename)
        self.output = io.StringIO()
        try:
            self.repo = git.Repo(search_parent_directories=True)
        except git.exc.InvalidGitRepositoryError:
            logger.critical('uji must be run from within a git tree')
            sys.exit(1)

        if target_directory is None:
            target_directory = self._find_dirname(Path(filename).stem)

        self.target_directory = target_directory

    def _find_dirname(self, prefix):
        assert prefix

        t = time.strftime('%Y-%m-%d')
        postfix = 0

        while True:
            dirname = f'{prefix}-{t}.{postfix}'
            if not Path(dirname).exists():
                break
            postfix += 1

        return dirname

    def generate(self):
        logger.debug(f'Loading template file "{self.filename}"')
        self.yaml = ExtendedYaml.load_from_file(self.filename)
        self._validate()

        logger.debug(f'target directory is: {self.target_directory}')
        Path(self.target_directory).mkdir()
        (Path(self.target_directory) / '.uji').touch(exist_ok=True)

        self._process()

        # save the combined yaml file. The version is hidden away, so we
        # need to manually add it again before writing it out
        outfile = Path(self.target_directory) / self.filename.name
        with open(outfile, 'w') as fd:
            data = deepcopy(self.yaml.data)
            data['version'] = self.yaml.version
            yaml.dump(data, stream=fd, default_flow_style=False)

        self.repo.index.add([os.fspath(outfile)])

        # record log goes into dirname/yamlfile.md
        outfile = self.filename.stem + '.md'
        outfile = Path(self.target_directory) / outfile
        with open(outfile, 'w') as fd:
            print(self.output.getvalue(), file=fd)

        # symlink to the most recent directory
        latest = Path('uji-latest')
        if not latest.exists() or latest.is_symlink():
            if latest.is_symlink():
                latest.unlink()
            latest.symlink_to(self.target_directory)
            self.repo.index.add([os.fspath(latest)])

        self.repo.index.add([os.fspath(outfile)])
        self.repo.index.commit(f'New uji test run - {self.target_directory}')

        print(f'Your test records and log files are')
        print(f'  {self.target_directory}/')
        for file in Path(self.target_directory).glob("**/*"):
            print(f'  {file}')

        print(f'Run "git reset HEAD~" to throw them away')

    def _validate(self):
        try:
            if self.yaml.version != 1:
                raise YamlError(f'YAML version must be 1')
        except AttributeError:
            # Missing version tag is interpreted as version 1
            pass

        actor_names = []

        for section, data in self.yaml.items():
            if not isinstance(data, dict):
                raise YamlError(f'Section {section} must be a dictionary')

            if section == 'file':
                continue

            if section == 'generic':
                raise YamlError(f'Keywoard "generic" is reserved and cannot be used for section names')

            if not data.get('type'):
                raise YamlError(f'Section {section} does not have a type')

            if data['type'] not in ['actor', 'test', 'log']:
                raise YamlError(f'Section {section} has invalid type "{data["type"]}')

            if data['type'] == 'actor':
                if 'name' in data:
                    name = data['name']
                    if name in actor_names:
                        raise YamlError(f'Duplicate actor name "{name}"')
                    actor_names.append(name)

            if data['type'] == 'test':
                if 'tests' not in data and 'logs' not in data:
                    raise YamlError(f'Section {section} doesn\'t have tests or logs')

                for f, fs in data.get('filter', {}).items():
                    if not isinstance(fs, list):
                        raise YamlError(f'Section {section} filter {f} must be a list')

                if 'logs' in data:
                    if 'files' not in data['logs'] and 'commands' not in data['logs']:
                        raise YamlError(f'Section {section} doesn\'t have log files or commands')

                    if 'files' in data['logs']:
                        if not isinstance(data['logs']['files'], list):
                            raise YamlError(f'Section {section} file list is not a list')

                    if 'commands' in data['logs']:
                        if not isinstance(data['logs']['commands'], list):
                            raise YamlError(f'Section {section} command list is not a list')

                    for command in data['logs'].get('commands', []):
                        if 'run' not in command:
                            raise YamlError(f'Command in {section} doesn\'t have run ')

    def _process(self):
        self.actors = collections.OrderedDict()

        # The actor for filter-less tests
        default_actor = UjiNew.Actor.default_actor()
        self.actors[default_actor.id] = default_actor

        # We have tests from the yaml file (this one) and
        # the class' self.tests which is the expanded lists after
        # duplicating each test for the respective actor.
        tests = []

        for section, sdata in self.yaml.items():
            if section == 'file':
                continue

            stype = sdata['type']
            if stype == 'actor':
                actor = UjiNew.Actor(section, sdata)
                self.actors[section] = actor
                logger.debug(f'New actor: {actor}')
            elif stype == 'test':
                test = UjiNew.Test(section, sdata)
                tests.append(test)
                logger.debug(f'New test: {test}')
            else:
                raise YamlError(f'Unknown section type {stype}')

        if not tests:
            raise YamlError(f'Missing tests, so what\'s the point?')

        self.tests = self._link_tests_with_actors(tests)
        # Now that we've linked tests and actors we can create mangled path
        # names to save all the test-specific files to
        for test in self.tests:
            for f in test.files:
                f.make_path_name(test, self.target_directory)
            for c in test.commands:
                c.make_path_name(test, self.target_directory)

        self._write_md_file()
        self._generate_test_files()
        self._generate_check_file()

    def _link_tests_with_actors(self, tests):
        all_tests = []
        # We run through the actors in order because that will also give us
        # a 'natural' order of the tests in the self.tests list later
        for _, actor in self.actors.items():
            for test in tests:
                # Tests without filters go to the generic actor
                if not actor.tags:
                    if not test.filters:
                        dup = deepcopy(test)
                        actor.tests.append(dup)
                        dup.actor = actor
                        all_tests.append(dup)
                        logger.debug(f'test {test} matches {actor}')
                    continue

                if not test.filters:
                    continue

                # filtered tests
                for key, values in test.filters.items():
                    if key not in actor.tags:
                        break

                    tag = actor.tags[key]

                    excluded = [v[1:] for v in values if v[0] == '!']
                    if tag in excluded:
                        break

                    required = [v for v in values if v[0] != '!']
                    if not required and excluded:
                        required = ['__any__']

                    if ('__any__' not in required and
                        actor.tags[key] not in required):
                        break
                else:
                    dup = deepcopy(test)
                    actor.tests.append(dup)
                    dup.actor = actor
                    all_tests.append(dup)
                    logger.debug(f'test {test} matches {actor}')

        return all_tests

    def _write_md_file(self):
        self.fmt = MarkdownFormatter(self.output)
        self.fmt.h1('Uji')

        # FIXME: this is not ideal when we have multiple includes, it'll all
        # be jambled up in the wrong order. Remains to be seen whether
        # that's an issue.
        for key, content in self.yaml.get('file', {}).items():
            self.fmt.p(content)

        for _, actor in self.actors.items():
            self.fmt.h2(actor.name)
            if actor.description:
                self.fmt.p(actor.description)
            self._print_tests(actor)

    def _print_tests(self, actor):
        with self.fmt.checkbox_list() as cb:
            for test in actor.tests:
                for instruction in test.tests:
                    cb.checkbox(instruction)
                    logger.debug(f'{actor.id}.{test.id} - {instruction}')
                for f in test.files:
                    # test file path contains the target directory but we
                    # need the one relative to within that directory
                    fpath = Path(f.path).relative_to(Path(self.target_directory))
                    cb.file_attachment(f.filename, fpath)
                for command in test.commands:
                    if command.path:
                        cpath = Path(command.path).relative_to(Path(self.target_directory))
                    else:
                        cpath = None
                    cb.command_output(command.run, command.description, command.output, cpath)

    def _generate_test_files(self):
        # pre-generate the test files we want to save the various outputs
        # to. Those files are yaml-compatible to begin with, we could read
        # them back to get the info we need to auto-fill those.
        for test in self.tests:
            for f in test.files:
                with open(f.path, 'w') as fd:
                    print(f'file: {f.filename}', file=fd)
                self.repo.index.add([os.fspath(f.path)])
            for c in test.commands:
                if c.path:
                    with open(c.path, 'w') as fd:
                        print(f'run: {c.run}', file=fd)
                    self.repo.index.add([os.fspath(c.path)])

    def _generate_check_file(self):
        precheck = Path(self.target_directory) / 'uji-check'
        with open(precheck, 'w') as fd:
            print(dedent(f'''\
                    #!/bin/sh
                    #
                    # This file is automatically executed by uji view.
                    # Return a nonzero exit code if any requirements fail.

                    exit 0
                    '''), file=fd)
            precheck.chmod(precheck.stat().st_mode | stat.S_IXUSR)


class KeymappingFlags(enum.Enum):
    ONLY_ON_CHECKBOX = enum.auto()
    ACTIVE_IN_HELP = enum.auto()
    UPLOAD = enum.auto()
    EXECUTE = enum.auto()


class Keymapping(object):
    def __init__(self, key, help, func, flags=None):
        self.key = key
        self.help = help
        self.func = func
        self.flags = flags or []

    @property
    def short_help(self):
        if self.help[0] == self.key:
            return f'({self.help[0]}){self.help[1:]}'
        else:
            return f'({self.key}) {self.help}'


class Dimension():
    def __init__(self, w, h):
        self.width, self.height = w, h


class UjiView(object):
    CURSOR = '⇒ '

    def __init__(self, directory):
        try:
            self.repo = git.Repo(search_parent_directories=True)
        except git.exc.InvalidGitRepositoryError:
            logger.critical('uji must be run from within a git tree')
            sys.exit(1)

        directory = Path(directory).resolve()
        mds = directory.glob('*.md')
        if not mds:
            raise ValueError(f'Cannot find a markdown file in {directory}')
        else:
            md = next(mds)
            try:
                next(mds)
                logger.warning('Multiple markdown files found, using "{md}"')
            except StopIteration:
                pass
        self.directory = directory
        self.mdfile = md

        self.console = rich.console.Console(theme=theme)

        # we keep the lines from the source file separate from the rendered
        # ones, the rendered ones are throwaways
        self.lines = open(md).readlines()
        self.stop = False
        self.restart = True
        self.view_offset = 0
        self.cursor_offset = 0
        self.error = None
        self.show_filename_enabled = True
        self.display_help = False

        keymap = (
            Keymapping('KEY_ESCAPE', 'quit/exit help', flags=[KeymappingFlags.ACTIVE_IN_HELP], func=self.exit),
            Keymapping('q', 'quit/exit help', flags=[KeymappingFlags.ACTIVE_IN_HELP], func=self.exit),
            Keymapping('j', 'down', func=self.cursor_down),
            Keymapping('k', 'up', func=self.cursor_up),
            Keymapping('KEY_DOWN', 'down', func=self.cursor_down),
            Keymapping('KEY_UP', 'down', func=self.cursor_up),
            Keymapping(' ', 'page down', func=self.page_down),
            Keymapping('n', 'next', func=self.next),
            Keymapping('p', 'previous', func=self.previous),
            Keymapping('r', 'run command', flags=[KeymappingFlags.ONLY_ON_CHECKBOX, KeymappingFlags.EXECUTE], func=self.execute_command),
            Keymapping('t', 'toggle', flags=[KeymappingFlags.ONLY_ON_CHECKBOX], func=self.toggle),
            Keymapping('u', 'upload', flags=[KeymappingFlags.ONLY_ON_CHECKBOX, KeymappingFlags.UPLOAD], func=self.upload),
            Keymapping('e', 'editor', func=self.editor),
            Keymapping('f', 'show filenames', func=self.show_filenames),
            Keymapping('?', 'help', func=self.show_help, flags=[KeymappingFlags.ACTIVE_IN_HELP]),
            Keymapping('S', 'skip test', flags=[KeymappingFlags.ONLY_ON_CHECKBOX], func=self.skip_test),
            Keymapping('P', 'pass test', flags=[KeymappingFlags.ONLY_ON_CHECKBOX], func=self.pass_test),
            Keymapping('F', 'fail test', flags=[KeymappingFlags.ONLY_ON_CHECKBOX], func=self.fail_test),
        )
        self.keymap: Dict[str, Keymapping] = {k.key: k for k in keymap}

        # curtsies doesn't handle bg/fg properly, so we hack it up this way
        def handler(signal, frame):
            self.stop = True
            self.restart = True
            print('\033c')
            print('Press enter to re-render')
        signal.signal(signal.SIGCONT, handler)

    @property
    def current_line(self) -> str:
        return self.lines[self.cursor_offset]

    @current_line.setter
    def current_line(self, value: str) -> None:
        self.lines[self.cursor_offset] = value

    def _render_markdown(self, lines) -> List[str]:
        in_code_section = False

        rendered = []

        for l in lines:
            l = l[:-1]  # drop trailing \n
            if l.lstrip().startswith('```'):
                in_code_section = not in_code_section
                if in_code_section:
                    l = f'[code] {" " * 80}'
                else:
                    l = f'{" " * 80}[/code]'
            elif in_code_section:
                filler = ' ' * (80 - len(l))
                l = f' {l}{filler}'
            else:
                # bold
                l = re.sub(r'\*\*([^*]*)\*\*', rf'[bold]\1[/bold]', l)
                # italic
                l = re.sub(r'([^*])\*([^*]*)\*([^*])', rf'\1[underline]\2\3[/underline]', l)
                # links
                expr = r'\[([^\[(]*)\]\((.*)\)'
                if self.show_filename_enabled:
                    l = re.sub(expr, rf'[filename]\1[/filename]', l)
                else:
                    l = re.sub(expr, rf'[filename]\2[/filename]', l)
                # inline code
                l = re.sub(r'`([^`]*)`', rf'[inline]\1[/inline]', l)

                # ###-style headers
                # we're stripping the ## here and thus need to adjust the
                # filler width
                l = re.sub(r'^(#{1,}\s?)(.*)',
                           lambda m: f'[header]{m.group(2)}{" " * (80 - len(m.group(1)) - len(m.group(2)))}[/header]', l)

                # checkboxes [ ], [x] or [X], must be escaped with one backslah (e.g. \[x]) to prevent rich from parsing it as markup
                l = re.sub(r'^(\s*- )(\[[ xX]\] )(.*)', r'[checkbox]\1\\\2\3[/checkbox]', l)

            rendered.append(l)

        # poor man's header section detection
        # we check against the original lines - in case we have markdown in
        # the header the string lengths may not match up otherwise
        for idx, l in list(enumerate(lines[:-1])):
            nextline = lines[idx + 1]
            if re.match(r'^[=\-._]{3,}$', nextline) and len(l) == len(nextline):
                r1 = rendered[idx]
                r2 = rendered[idx + 1]
                filler = ' ' * (80 - len(r1))
                rendered[idx] = f'[header]{r1}{filler}[/header]'
                rendered[idx + 1] = f'[header]{r2}{filler}[/header]'

        with self.console.capture() as capture:
            self.console.print("\n".join(rendered))
        rendered = capture.get().split('\n')

        return rendered

    def _update_cursor(self, new_position):
        if new_position < 0:
            new_position = 0
        elif new_position >= len(self.lines):
            new_position = len(self.lines) - 1

        if new_position == self.cursor_offset:
            return

        self.cursor_offset = new_position

        if self.cursor_offset >= self.view_offset + self.window.height - 1:
            self._update_view(self.view_offset + self.window.height // 2)
        elif self.cursor_offset < self.view_offset:
            self._update_view(self.view_offset - self.window.height // 2)

    def _update_view(self, new_position):
        if new_position < 0:
            new_position = 0
        elif new_position > len(self.lines) - self.window.height // 2:
            new_position = len(self.lines) - self.window.height // 2

        if new_position == self.view_offset:
            return

        self.view_offset = new_position
        if self.cursor_offset < self.view_offset:
            self._update_cursor(self.view_offset)
        elif self.cursor_offset > self.view_offset + self.window.height:
            self._update_cursor(self.view_offset + self.window.height)
        self.rerender()

    def _handle_input(self, c):
        try:
            mapping = self.keymap[c]
        except KeyError:
            try:
                mapping = self.keymap[c.name]
            except KeyError:
                return

        if not self.display_help or KeymappingFlags.ACTIVE_IN_HELP in mapping.flags:
            mapping.func()

    def _line_split_by_width(self, line, max_len):
        return [(line[i:i + max_len]) for i in range(0, len(line), max_len)]

    def _insert(self, offset, line, target=None):
        l = self._sanitize(line)
        max_len = 250

        if target is None:
            target = self.lines

        # split our line into max_len-sized chunks
        lines = self._line_split_by_width(l, max_len)

        # then append them as one line each with trailing newline
        for l in lines:
            eol = '\n' if len(l) >= max_len else ''
            target.insert(offset, l + eol)
            offset += 1
        return offset

    def exit(self):
        if self.display_help:
            self.display_help = False
            self.rerender()
        else:
            self.quit()

    def quit(self):
        self.stop = True
        if self.repo.is_dirty():
            self.repo.index.commit('uji view changes')

    def cursor_down(self):
        self._update_cursor(self.cursor_offset + 1)

    def cursor_up(self):
        self._update_cursor(self.cursor_offset - 1)

    def page_down(self):
        self._update_view(self.view_offset + self.window.height)

    def next(self):
        for idx, l in enumerate(self.lines[self.cursor_offset + 1:]):
            if self.is_checkbox(l):
                self._update_cursor(self.cursor_offset + 1 + idx)
                break

    def previous(self):
        for idx, l in reversed(list(enumerate(self.lines[:self.cursor_offset]))):
            if self.is_checkbox(l):
                self._update_cursor(idx)
                break

    def is_checkbox(self, line):
        return re.match(r'^\s*- \[[ xX]\].*', line) is not None

    def mark(self):
        line = self.current_line
        if not self.is_checkbox(line):
            return

        line = re.sub(r'^(\s*)- \[ \](.*)', r'\1- [x]\2', line)
        self.current_line = line
        self.writeout()
        self._redraw()

    def unmark(self):
        line = self.current_line
        if not self.is_checkbox(line):
            return

        line = re.sub(r'^(\s*)- \[[xX]\](.*)', r'\1- [ ]\2', line)
        self.current_line = line
        self.writeout()
        self._redraw()

    def toggle(self):
        line = self.current_line
        if not self.is_checkbox(line):
            return

        if re.match(r'^(\s*)- \[ \](.*)', line):
            self.mark()
        else:
            self.unmark()

        self.next()

    def upload(self):
        line = self.current_line
        if not self.is_checkbox(line) or "📎" not in line:
            return

        match = re.match(r'.* \[(.*)\]\((.*)\).*', line)
        if not match:
            logger.error(f'Failed to match attachment line: {line}')
            return

        # filenames are in `backticks`
        filename = re.sub(r'`?([^`]*)`?', r'\1', match[1])
        path = self.directory / match[2]

        try:
            import shutil
            shutil.copyfile(filename, path)
            self.repo.index.add([os.fspath(path)])
            self.mark()
        except Exception as e:
            logger.error(f'Failed to copy {filename}: {e}')

    def remove_code_block_content(self, lines, from_offset=0):
        new_lines = lines[:from_offset + 1]
        codeblock_offset = -1
        in_codeblock = False
        for line in lines[from_offset + 1:]:
            if in_codeblock:
                if '```' in line:
                    in_codeblock = False
                else:
                    # remove existing output
                    continue
            if codeblock_offset < 0:
                # find the existing ``` markers
                if '```' in line:
                    in_codeblock = True
                    codeblock_offset = len(new_lines) + 1
                # new codeblock, enforce our markers, right below cursor_offset
                if self.is_checkbox(line):
                    codeblock_offset = self._insert(self.cursor_offset + 1, '```\n', target=new_lines)
                    self._insert(codeblock_offset, '```\n', target=new_lines)
            # rest is going to be forwarded as it was
            new_lines.append(line)

        # return the index where to store the output of the command
        return new_lines, codeblock_offset

    def _sanitize(self, line):
        return line.replace('\t', '    ')

    def execute_command(self):
        line = self.current_line
        if not self.is_checkbox(line) or "⚙" not in line:
            return

        # list of regex to deduce the type of command to be run
        command_re = {
                'attach': r'^(\s*)- \[.\].* \[`(.*)`\]\((.*)\).*',
                'human': r'^(\s*)- \[.\].* `(.*)`: \*\*(.*)\*\*$',
                'single': r'^(\s*)- \[.\].* `(.*)`: `(.*)`$',
                'multi': r'^(\s*)- \[.\].* `(.*)`:$',
                'exitcode': r'^(\s*)- \[.\].* `(.*)`$',
        }

        command_type = None
        command_match = None

        for type_c, re_c in command_re.items():
            match = re.match(re_c, line)
            if match:
                command_type = type_c
                command_match = match
                break

        if command_type is None:
            logger.error(f'Failed to match run command line: {line}')
            return

        command = match[2]
        output = []
        insert_offset = self.cursor_offset + 1
        offset = -1

        if command_type == 'multi':
            self.lines, offset = self.remove_code_block_content(self.lines, self.cursor_offset)
            self.writeout()
            self._redraw()
            self._render()


        try:
            import subprocess

            proc = subprocess.Popen(command, shell=True, universal_newlines=True,
                                    bufsize=0,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

            while proc.poll() is None:
                if command_type == 'multi':
                    line = proc.stdout.readline()
                    while line:
                        offset = self._insert(offset, line)
                        output.append(line)
                        self.writeout()
                        self._redraw()
                        self._render()
                        line = proc.stdout.readline()
                else:
                    output.extend(proc.stdout.readlines())
            result = proc.poll()
        except KeyboardInterrupt:
            proc.terminate()
            time.sleep(0.2)
            if proc.poll() is None:
                proc.kill()
            logger.error('execution aborted')
            return
        except Exception as e:
            logger.error(f'Failed to execute `{command}`: {e}')
            return

        lines = proc.stdout.readlines()
        if command_type == 'multi':
            for line in lines:
                offset = self._insert(offset, line)
            self.writeout()
            self._redraw()
            self._render()
        output.extend(lines)

        # append the return code to the logs
        indent = len(match[1])
        result_line = f'{" " * (indent)} - result code: {int(result)}\n'

        # check if the result was already given:
        res_match = re.match(f'{" " * (indent)} - result code:.*', self.lines[insert_offset])
        if res_match:
            self.lines[insert_offset] = result_line
            insert_offset += 1
        else:
            insert_offset = self._insert(insert_offset, result_line)

        if command_type == 'exit_code':
            # no need to do anything more for exit code
            pass
        elif command_type == 'attach':
            filename = self.directory / match[3]
            with open(filename, 'w') as f:
                f.write(''.join(output))
            self.repo.index.add([os.fspath(filename)])
        elif command_type == 'single':
            line = re.sub(r'(.*) `(.*)`:.*\n', r'\1 `\2`:', line)
            if len(output) == 1:
                l = self._sanitize(output[0].strip())
                line += f' `{l}`'
            elif len(output) == 0:
                line += f' `<no output>`'
            line += '\n'

            # overwrite the current line to set the output
            self.current_line = line

            # multi-lines output
            if len(output) > 1:
                insert_offset = self._insert(insert_offset, '```\n')
                for l in output:
                    insert_offset = self._insert(insert_offset, l)
                insert_offset = self._insert(insert_offset, '```\n')
        else:
            return

        self.mark()
        self.next()

    def _prefix_with(self, prefix: str, allowed_prefixes=['PASS', 'SKIP', 'FAIL']):
        '''
        Prefix the current checkbox item with **SKIP** or similar so we get a box like
            - [ ] **SKIP** the existing text
        '''
        assert prefix in allowed_prefixes  # sanity check only

        line = self.current_line
        if not self.is_checkbox(line):
            return

        m = re.match(r'^(\s* - \[.\]\s*)(.*)', line)
        if not m:
            return

        md_checkbox = m[1]
        rest_of_line = m[2]

        def pfmt(p):
            return f'**{p}** '

        for p in [pfmt(x) for x in allowed_prefixes]:
            if rest_of_line.startswith(p):
                rest_of_line = rest_of_line[len(p):]

        line = f'{md_checkbox}{pfmt(prefix)}{rest_of_line}\n'
        self.current_line = line
        self.writeout()
        self._redraw()
        # Explicitly passing/failing/skipping means this test is done - manually untoggle if need be
        self.mark()
        self.next()

    def skip_test(self):
        self._prefix_with("SKIP")

    def pass_test(self):
        self._prefix_with("PASS")

    def fail_test(self):
        self._prefix_with("FAIL")

    def editor(self):
        editor = os.environ.get('EDITOR')
        if not editor:
            return

        subprocess.call([editor, self.mdfile, f'+{self.cursor_offset + 1}'])
        self.lines = open(self.mdfile).readlines()
        self.rerender()

    def show_filenames(self):
        self.show_filename_enabled = not self.show_filename_enabled
        self.rerender()

    def show_help(self):
        self.display_help = not self.display_help
        self.rerender()

    def writeout(self):
        with open(self.mdfile, 'w') as fd:
            fd.write(''.join(self.lines))
        self.repo.index.add([os.fspath(self.mdfile)])

    def _draw_help_screen(self) -> List[str]:
        rendered = ['+' + '-' * 32 + '+']
        for _, v in self.keymap.items():
            str = f'{v.key}: {v.help}'
            rendered.append(f'| {str:30s} |')
        rendered.append('+' + '-' * 32 + '+')

        return rendered

    def _redraw(self):
        self._update_cursor(self.cursor_offset)

        # Note: this assumes that our rendering process never inserts or removes lines
        # Also - if the line is wider than the terminal, interesting things happen.
        # But we can't easily clip because all the ansi escape codes make our strings longer
        # than they are.
        rendered = self._render_markdown(self.lines)
        self.line_buffer = rendered[self.view_offset:self.view_offset + self.window.height]

    def _redraw_help_screen(self):
        rendered = self._draw_help_screen()
        self.line_buffer = rendered

    def _render(self):
        cursor_prefix = ' ' * len(self.CURSOR)
        print(self.term.home, end='')
        for idx, line in enumerate(self.line_buffer[:-1]):
            print(cursor_prefix + line)

        # now draw in the cursor
        print(self.term.move_xy(0, self.cursor_offset - self.view_offset) + self.CURSOR, end='')

        # and the statusline
        console = rich.console.Console(theme=theme)
        with console.capture() as capture:
            console.print(self.statusline)

        statusline = capture.get().rstrip()
        statusline_idx = self.window.height - 1

        print(self.term.move_xy(0, statusline_idx) + statusline, end='', flush=True)

    def _clear_screen(self):
        print(self.term.move_xy(0, 0)+ self.term.clear, end='', flush=True)

    def rerender(self):
        self._clear_screen()
        if self.display_help:
            self._redraw_help_screen()
        else:
            self._redraw()

    @property
    def statusline(self):
        if self.error:
            return f'[error]{self.error}[/error]'

        commands = [self.keymap[k] for k in ['j', 'k', 'n', 'p', 'e', 'q', 'r', 't', 'u', 'f']]

        statusline = ['[statusline] ---']
        for k in commands:
            s = k.short_help

            # gray out toggle/upload for non-checkboxes
            if KeymappingFlags.ONLY_ON_CHECKBOX in k.flags:
                line = self.current_line
                if (not self.is_checkbox(line) or
                        (KeymappingFlags.UPLOAD in k.flags and '📎' not in line) or
                        (KeymappingFlags.EXECUTE in k.flags and '⚙' not in line)):
                    s = f'[statusline_inactive]{s}[/statusline_inactive]'
            statusline.append(f'[statusline_active]{s}[/statusline_active]')

        statusline.append(' ---[/statusline]')
        return ' '.join(statusline)

    def run(self):
        while self.restart:
            self.stop = False
            self.restart = False
            term = blessed.Terminal()
            self.term = term
            with term.fullscreen(), term.cbreak(), term.hidden_cursor():
                self.window = Dimension(term.width, term.height)
                self._redraw()
                self._render()

                while not self.stop:
                    self._handle_input(term.inkey())
                    self._render()


def uji_setup(directory):
    try:
        directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        logger.critical(f'Directory {directory} already exists')
        sys.exit(1)

    README = directory / 'README.md'
    with open(README, 'w') as fd:
        fd.write(f'# Uji test repository\n\nPlease fill me in\n')

    import urllib.request

    yamlfile = directory / f'{directory.name}.yaml'

    try:
        URL = 'https://raw.githubusercontent.com/whot/uji/main/examples/example.yaml'
        with urllib.request.urlopen(URL, timeout=5) as response:
            content = response.read().decode()
    except Exception as e:
        logger.error(f'Failed to fetch the example tests from upstream: {e}')
        logger.info(f'Using a minimal example instead')
        content = dedent(f'''\
        # Minimal uji template. Please edit.

        version: 1
        file:
            {yamlfile.name}: |
              This is a minimal example generated by uji setup. Please edit
              accordingly to add your tests.

        actor1:
            type: actor
            name: Some piece of hardware
            tags:
              tag1: value1

        test1:
            type: test
            filter:
              tag1: [value1]
            tests:
            - add the test cases
        ''')

    with open(yamlfile, 'w') as fd:
        fd.write(content)

    repo = git.Repo.init(directory)
    repo.index.add([os.fspath(yamlfile.name)])
    repo.index.add([os.fspath(README.name)])
    repo.index.commit(f'Initial setup for {directory.name}')

    print(f'New uji directory set up at\n{directory}/')
    for file in Path(directory).glob('*'):
        print(f'  {file}')
    print(dedent(f'''\
          Please edit the test templates at {yamlfile} and git commit them.

          To start a new test set:
              cd {directory}
              uji new {yamlfile.name}
              uji view {yamlfile.stem}-<date>
          '''))


def uji_check(directory):
    precheck = Path(directory) / 'uji-check'
    if not precheck.exists():
        return

    try:
        subprocess.check_output([os.fspath(precheck)], stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        logger.critical(f'uji-check failed with exit code {e.returncode}. Aborting.')
        if e.output:
            logger.critical(f'stdout/stderr from the uji-check script:')
            print(e.output.decode())
        sys.exit(1)


##########################################
#               The CLI interface        #
##########################################

# top-level command
@click.group()
@click.option('-v', '--verbose', count=True, help='increase verbosity')
@click.option('--quiet', 'verbose', flag_value=0)
def uji(verbose):
    '''
    uji generates checklists from template files and stores those checklists in git.

    To get started, run 'uji setup' followed by 'uji new', then `uji view`.
    '''
    verbose_levels = {
        0: logging.ERROR,
        1: logging.INFO,
        2: logging.DEBUG,
    }

    logger.setLevel(verbose_levels.get(verbose, 0))
    # all the actual work is done in the subcommands


# subcommand: uji new
@uji.command()
@click.argument('template', type=click.Path())
@click.argument('directory', required=False, type=click.Path())
def new(template, directory):
    '''Create a new test log directory from a YAML template.'''
    try:
        if not Path(template).exists():
            for suffix in ('.yaml', '.yml'):
                alternative = Path(f"{template}{suffix}")
                if alternative.exists():
                    template = alternative
        UjiNew(template, directory).generate()
    except YamlError as e:
        logger.critical(f'Failed to parse YAML file: {e}')


# subcommand: uji view
@uji.command()
@click.argument('directory',
                type=click.Path(file_okay=False, dir_okay=True, exists=True),
                required=False)
def view(directory):
    '''
    View and update test logs in DIRECTORY

    If no directory is given, default to the 'uji-latest' directory
    symlink created by uji new or the most recently created directory.
    '''
    if directory is None:
        if Path('uji-latest').exists():
            directory = 'uji-latest'
        else:
            dirs = [x for x in Path('.').iterdir() if x.is_dir() and not x.name.startswith('.') and (x / '.uji').exists()]
            dirs.sort(key=lambda f: os.path.getctime(f), reverse=True)
            if not dirs:
                click.echo("Unable to find a matching uji directory")
                sys.exit(1)
            directory = dirs[0]

    uji_check(directory)
    UjiView(directory).run()


# subcommand: uji setup
@uji.command()
@click.argument('directory',
                type=click.Path(file_okay=False, dir_okay=True, exists=False))
def setup(directory):
    '''Setup DIRECTORY as new uji test result directory'''
    directory = Path(directory)
    uji_setup(directory)


# subcommand: uji check
@uji.command()
@click.argument('directory',
                type=click.Path(file_okay=False, dir_okay=True, exists=False))
def check(directory):
    '''Run the uji-check script in DIRECTORY'''
    uji_check(directory)


def main(args=sys.argv):
    uji()


if __name__ == '__main__':
    main()
