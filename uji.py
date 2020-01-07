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

import click
import collections
import curtsies
import git
import io
import logging
import os
import re
import signal
import stat
import subprocess
import sys
import time
import yaml
from copy import deepcopy
from pathlib import Path
from textwrap import dedent


class Colors:
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    LIGHT_GRAY = '\033[37m'
    DARK_GRAY = '\033[90m'
    LIGHT_RED = '\033[91m'
    LIGHT_GREEN = '\033[92m'
    LIGHT_YELLOW = '\033[93m'
    LIGHT_BLUE = '\033[94m'
    LIGHT_MAGENTA = '\033[95m'
    LIGHT_CYAN = '\033[96m'
    WHITE = '\033[97m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    BG_BLACK = '\u001b[40m'
    BG_RED = '\u001b[41m'
    BG_GREEN = '\u001b[42m'
    BG_YELLOW = '\u001b[43m'
    BG_BLUE = '\u001b[44m'
    BG_MAGENTA = '\u001b[45m'
    BG_CYAN = '\u001b[46m'
    BG_WHITE = '\u001b[47m'
    BG_BRIGHT_BLACK = '\u001b[40;1m'
    BG_BRIGHT_RED = '\u001b[41;1m'
    BG_BRIGHT_GREEN = '\u001b[42;1m'
    BG_BRIGHT_YELLOW = '\u001b[43;1m'
    BG_BRIGHT_BLUE = '\u001b[44;1m'
    BG_BRIGHT_MAGENTA = '\u001b[45;1m'
    BG_BRIGHT_CYAN = '\u001b[46;1m'
    BG_BRIGHT_WHITE = '\u001b[47;1m'

    @classmethod
    def format(cls, message):
        '''
        Format the given message with the colors, always ending with a
        reset escape sequence.

        .. param: message

        The to-be-colorized message. Use the colors prefixed with a dollar
        sign, e.g. ``Colors.format(f'$RED{somevar}$RESET')``

        '''
        for k, v in cls.__dict__.items():
            if not isinstance(v, str) or v[1] != '[':
                continue
            message = message.replace('$' + k, v)
        return message + cls.RESET


class ColorFormatter(logging.Formatter):
    def format(self, record):
        COLORS = {
            'DEBUG': Colors.LIGHT_GRAY,
            'INFO': Colors.LIGHT_GREEN,
            'WARNING': Colors.YELLOW,
            'ERROR': Colors.LIGHT_RED,
            'CRITICAL': Colors.RED,
        }
        message = logging.Formatter.format(self, record)
        message = message.replace(f'$COLOR', COLORS[record.levelname])
        return Colors.format(message)


log_format = '$COLOR%(levelname)s: %(message)s'
logger_handler = logging.StreamHandler()
logger_handler.setFormatter(ColorFormatter(log_format))
logger = logging.getLogger('uji')
logger.addHandler(logger_handler)
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
        self.fprint(text)
        self.fprint('=' * len(text))

    def h2(self, text):
        self.fprint(text)
        self.fprint('-' * len(text))

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
            self._checkbox(text, indent, symbol='⍿')

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
                self.checkbox_command(f'`{command}`: <strong>ADD COMMENTS HERE</strong>')
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
                    if ('__any__' not in values and
                            actor.tags[key] not in values):
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

        # we keep the lines from the source file separate from the rendered
        # ones, the rendered ones are throwaways
        self.lines = open(md).readlines()
        self.stop = False
        self.restart = True
        self.view_offset = 0
        self.cursor_offset = 0
        self.error = None
        self.show_filename_enabled = True

        # curtsies doesn't handle bg/fg properly, so we hack it up this way
        def handler(signal, frame):
            self.stop = True
            self.restart = True
            print('\033c')
            print('Press enter to re-render')
        signal.signal(signal.SIGCONT, handler)

    def _render_markdown(self, lines):
        in_code_section = False

        rendered = []

        for l in lines:
            l = l[:-1]  # drop trailing \n
            if l.startswith('```'):
                in_code_section = not in_code_section
                l = f'$BG_BRIGHT_YELLOW {" " * 80}$RESET'
            elif in_code_section:
                filler = ' ' * (80 - len(l))
                l = f'$BG_BRIGHT_YELLOW {l}{filler}$RESET'
            else:
                # bold
                l = re.sub(r'\*\*([^*]*)\*\*', rf'$BOLD\1$RESET', l)
                # italic
                l = re.sub(r'([^*])\*([^*]*)\*([^*])', rf'\1$UNDERLINE\2$RESET\3', l)
                # links
                expr = r'\[([^\[(]*)\]\((.*)\)'
                if self.show_filename_enabled:
                    l = re.sub(expr, rf'$UNDERLINE$BLUE\1$RESET', l)
                else:
                    l = re.sub(expr, rf'$UNDERLINE$BLUE\2$RESET', l)
                # inline code
                l = re.sub(r'`([^`]*)`', rf'$RED\1$RESET', l)

                # ###-style headers
                # we're stripping the ## here and thus need to adjust the
                # filler width
                l = re.sub(r'^(#{1,}\s?)(.*)',
                           lambda m: f'$BOLD$BG_BRIGHT_CYAN{m.group(2)}{" " * (80 - len(m.group(1)) - len(m.group(2)))}$RESET', l)

                # checkboxes [ ], [x] or [X]
                l = re.sub(r'^\s*(- \[[ xX]\] )(.*)', rf'$GREEN\1\2', l)

            rendered.append(Colors.format(l))

        # poor man's header section detection
        # we check against the original lines - in case we have markdown in
        # the header the string lengths may not match up otherwise
        for idx, l in list(enumerate(lines[:-1])):
            nextline = lines[idx + 1]
            if re.match(r'^[=\-._]{3,}$', nextline) and len(l) == len(nextline):
                r1 = rendered[idx]
                r2 = rendered[idx + 1]
                filler = ' ' * (80 - len(r1))
                rendered[idx] = Colors.format(f'$BOLD$BG_BRIGHT_CYAN{r1}$BOLD$BG_BRIGHT_CYAN{filler}')
                rendered[idx + 1] = Colors.format(f'$BOLD$BG_BRIGHT_CYAN{r2}$BOLD$BG_BRIGHT_CYAN{filler}')

        return rendered

    def _init_buffer(self, window, lines):
        # extra height so we can scroll off the bottom
        # fixed width because we don't handle resizes
        self.line_buffer = curtsies.FSArray(len(lines) + window.height, 256)

        curlen = len(self.CURSOR)
        for idx, l in enumerate(self.rendered):
            msg = curtsies.fmtstr(l)
            self.line_buffer[idx, curlen:msg.width + curlen] = [msg]

    def _update_cursor(self, new_position):
        if new_position < 0:
            new_position = 0
        elif new_position >= len(self.lines):
            new_position = len(self.lines) - 1

        if new_position == self.cursor_offset:
            return

        curlen = len(self.CURSOR)
        self.line_buffer[self.cursor_offset, 0:curlen] = [' ' * curlen]
        self.cursor_offset = new_position
        self.line_buffer[self.cursor_offset, 0:curlen] = [self.CURSOR]

        if self.cursor_offset > self.view_offset + self.window.height:
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

    def _handle_input(self, window, c):
        mapping = {
            '<ESC>': self.quit,
            'q': self.quit,
            'j': self.cursor_down,
            'k': self.cursor_up,
            '<DOWN>': self.cursor_down,
            '<UP>': self.cursor_up,
            '<SPACE>': self.page_down,
            'n': self.next,
            'p': self.previous,
            't': self.toggle,
            'u': self.upload,
            'e': self.editor,
            'f': self.show_filenames,
        }

        try:
            func = mapping[c]
        except KeyError:
            pass
        else:
            func()

        return False

    def quit(self):
        self.stop = True
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
        line = self.lines[self.cursor_offset]
        if not self.is_checkbox(line):
            return

        line = re.sub(r'^(\s*)- \[ \](.*)', r'\1- [x]\2', line)
        self.lines[self.cursor_offset] = line
        self.writeout()
        self._redraw()

    def unmark(self):
        line = self.lines[self.cursor_offset]
        if not self.is_checkbox(line):
            return

        line = re.sub(r'^(\s*)- \[[xX]\](.*)', r'\1- [ ]\2', line)
        self.lines[self.cursor_offset] = line
        self.writeout()
        self._redraw()

    def toggle(self):
        line = self.lines[self.cursor_offset]
        if not self.is_checkbox(line):
            return

        if re.match(r'^(\s*)- \[ \](.*)', line):
            self.mark()
        else:
            self.unmark()

    def upload(self):
        line = self.lines[self.cursor_offset]
        if not self.is_checkbox(line) or "📎" not in line:
            return

        match = re.match(r'.* \[(.*)\]\((.*)\).*', line)
        if not match:
            logger.error('Failed to match attachment line: {line}')
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

    def writeout(self):
        with open(self.mdfile, 'w') as fd:
            fd.write(''.join(self.lines))
        self.repo.index.add([os.fspath(self.mdfile)])

    def _redraw(self):
        self.rendered = self._render_markdown(self.lines)
        self._init_buffer(self.window, self.lines)
        self._update_cursor(self.cursor_offset)

    def _render(self):
        # easiest to just swap the last line with our status line
        # than figuring out how to to this properl. curties doesn't
        # have a "draw on bottom line" method
        bottom_line_idx = self.view_offset + self.window.height - 1
        prev = self.line_buffer[bottom_line_idx]
        self.line_buffer[bottom_line_idx] = self.statusline
        self.window.render_to_terminal(self.line_buffer[self.view_offset:])
        self.line_buffer[bottom_line_idx] = prev

    def rerender(self):
        # Clear the screen, then re-render everything
        clearscreen = curtsies.FSArray(self.window.height, self.window.width)
        for idx, l in enumerate(clearscreen):
            clearscreen[idx] = [' ' * self.window.width]
        self.window.render_to_terminal(clearscreen)
        self._redraw()

    @property
    def statusline(self):
        if self.error:
            return Colors.format(f'$RED{self.error}')

        commands = {
            'j': 'up',
            'k': 'down',
            'n': 'next',
            'p': 'previous',
            'e': 'edit',
            'q': 'quit',
            't': 'toggle',
            'u': 'upload',
            'f': 'show filenames',
        }

        statusline = ['$BOLD ---']
        for k, v in commands.items():
            if v[0] == k:
                s = f'({k}){v[1:]}'
            else:
                s = f'({k}) {v}'

            # gray out toggle/upload for non-checkboxes
            if k == 't' or k == 'u':
                line = self.lines[self.cursor_offset]
                if (not self.is_checkbox(line) or
                        (k == 'u' and '📎' not in line)):
                    s = f'$LIGHT_GRAY{s}'
            statusline.append(f'$BOLD{s}$RESET')

        statusline.append('$BOLD ---')
        return Colors.format(' '.join(statusline))

    def run(self):
        while self.restart:
            self.stop = False
            self.restart = False
            with curtsies.FullscreenWindow() as window:
                self.window = window
                self._redraw()
                with curtsies.Input() as input_generator:
                    self._render()
                    for c in input_generator:
                        self._handle_input(window, c)
                        if self.stop:
                            break

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
        URL = 'https://raw.githubusercontent.com/whot/uji/master/examples/example.yaml'
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
              uji view {yamlfile.name}-<date>
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
    '''Create a new test log directory from a template'''
    try:
        UjiNew(template, directory).generate()
    except YamlError as e:
        logger.critical(f'Failed to parse YAML file: {e}')


# subcommand: uji view
@uji.command()
@click.argument('directory',
                type=click.Path(file_okay=False, dir_okay=True, exists=True))
def view(directory):
    '''View and update test logs in DIRECTORY'''
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
