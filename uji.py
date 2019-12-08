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

import collections
import logging
import argparse
import io
import yaml
import time
import sys
import git
import os
from copy import deepcopy
from pathlib import Path

from collections import UserDict

logger = logging.getLogger('testtmpl')


class YamlError(Exception):
    pass


class ExtendedYaml(UserDict):
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

    def __load(self, stream):
        data = self.__process_includes(stream)
        data = yaml.safe_load(data)
        if not isinstance(data, dict):
            raise YamlError('Invalid YAML data format, expected a dictionary')

        if data.get('extends'):
            raise YamlError('Invalid section name "extends", this is a reserved keyword')

        data = self.__process_extends(data)
        for k, v in data.items():
            self[k] = v

    def __process_includes(self, source, dest=None, level=0):
        if level > 10:
            return ''

        if dest is None:
            dest = io.StringIO()

        for line in source:
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

            if not getattr(self, 'include_path'):
                raise YamlError('Cannot include from a text stream')

            filename = line[len('include:'):].strip()
            with open(Path(self.include_path) / filename) as included:
                dest.write(self.__process_includes(included, dest, level + 1))

        return dest.getvalue()

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
                raise YamlError('Invalid section for "extends: {referenced}"')

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
            yml = ExtendedYaml()
            yml.include_path = Path(filename).parent
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

        def _checkbox(self, text, indent=0, symbol='⍿'):
            spaces = " " * indent * 2
            self.parent.fprint(f'{spaces} - [ ] {symbol} {text}')

        def checkbox(self, text, indent=0):
            self._checkbox(text, indent)

        def checkbox_attachment(self, text, indent=0):
            self._checkbox(text, indent, symbol='\U0001F4CE')

        def file_attachment(self, filename, path):
            self.checkbox_attachment(f'[`{filename}`]({path})')

        def command_output(self, command, description, output_type, filename=None):
            if output_type == 'exitcode':
                self.checkbox(f'`{command}`')
                if description:
                    self.parent.fprint(f'  - {description}')
                self.checkbox(f'SUCCESS', indent=1)
                self.checkbox(f'FAIL', indent=1)
            elif output_type == 'single':
                self.checkbox(f'`{command}`: `COMMAND OUTPUT`')
                if description:
                    self.parent.fprint(f'  - {description}')
            elif output_type == 'multi':
                self.checkbox(f'`{command}`:')
                if description:
                    self.parent.fprint(f'  - {description}')
                self.parent.fprint(f'```')
                self.parent.fprint(f'   COMMAND OUTPUT')
                self.parent.fprint(f'')
                self.parent.fprint(f'```')
            elif output_type == 'attach':
                self.checkbox_attachment(f'[`{command}`]({filename})')
                if description:
                    self.parent.fprint(f'  - {description}')
            elif output_type == 'human':
                self.checkbox(f'`{command}`: <strong>ADD COMMENTS HERE</strong>')
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
            logger.debug(self)

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
            logs = yaml.get('logs', None)
            if logs:
                self.files = [UjiNew.FileName(f) for f in logs.get('files', [])]
                self.commands = [UjiNew.Command(yaml) for yaml in logs.get('commands', [])]
            else:
                self.files = []
                self.commands = []
            self.actor = None
            logger.debug(self)

        def __str__(self):
            return f'UjiNew.Test: {self.id}: filters {self.filters}'

    class FileName(object):
        def __init__(self, filename):
            self.filename = filename
            self.path = None

        def make_path_name(self, test, directory):
            # Unicode Character 'DIVISION SLASH' (U+2215)
            filename = f'{test.actor.id}.{test.id}.{self.filename}'.replace('/', '∕')
            self.path = Path(directory) / filename

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

            # Unicode Character 'NO-BREAK SPACE' (U+00A0)
            # Unicode Character 'MINUS SIGN' (U+2212)
            run = self.run.replace(' ', '\u00A0').replace('-', '\u2212')
            filename = f'{test.actor.id}.{test.id}.{run}'
            self.path = Path(directory) / filename

    @classmethod
    def add_arguments(cls, parent_parser):
        p = parent_parser.add_parser('new', help='Instantiate a new test record')
        p.add_argument('template', type=str, help='Path to template file')
        p.add_argument('directory', type=str, nargs='?', help='Path to new directory')
        p.set_defaults(func=UjiNew.execute)

    @classmethod
    def execute(cls, args):
        UjiNew(args.template, args.directory).generate()

    def __init__(self, filename, target_directory):
        assert filename

        self.filename = Path(filename).name
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

        # save the combined yaml file
        outfile = Path(self.target_directory) / self.filename
        with open(outfile, 'w') as fd:
            yaml.dump(self.yaml.data, stream=fd, default_flow_style=False)

        self.repo.index.add([os.fspath(outfile)])

        # record log goes into dirname/yamlfile.md
        outfile = Path(self.filename).stem + '.md'
        outfile = Path(self.target_directory) / outfile
        with open(outfile, 'w') as fd:
            print(self.output.getvalue(), file=fd)

        self.repo.index.add([os.fspath(outfile)])

        print(f'Your test records and log files are')
        print(f'  {self.target_directory}/')
        for file in Path(self.target_directory).iterdir():
            print(f'  {file}')
        print(f'Run "git commit" to commit the changes, or "git reset" to throw them away')

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
                if 'logs' in data:
                    if 'files' not in data['logs'] and 'commands' not in data['logs']:
                        raise YamlError(f'Section {section} doesn\'t have log files or commands')
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
                self.actors[section] = UjiNew.Actor(section, sdata)
            elif stype == 'test':
                tests.append(UjiNew.Test(section, sdata))
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
                    continue

                # Tests with filters are matched up
                for tag, tagstr in actor.tags.items():
                    try:
                        if ('__any__' in test.filters[tag] or
                                tagstr in test.filters[tag]):
                            dup = deepcopy(test)
                            actor.tests.append(dup)
                            dup.actor = actor
                            all_tests.append(dup)
                    except KeyError:
                        pass

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
                    cb.file_attachment(f.filename, f.path)
                for command in test.commands:
                    cb.command_output(command.run, command.description, command.output, command.path)

    def _make_file_name(self, test, filename):
        # Unicode Character 'DIVISION SLASH' (U+2215)
        return f'{test.actor.id}.{test.id}.{filename}'.replace('/', '∕')

    def _generate_test_files(self):
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


class Uji(object):
    def __init__(self):
        pass

    def run(self, args):
        parser = argparse.ArgumentParser(description='Generate a test case template')
        parser.add_argument('--verbose', action='store_true', default=False, help='Verbose debugging output')
        subparsers = parser.add_subparsers(title='Commands', help='Available sub-commands')

        # Add the sub commands
        UjiNew.add_arguments(subparsers)

        args = parser.parse_args(args)
        logging.basicConfig(level=logging.DEBUG if args.verbose else logging.ERROR)
        if not hasattr(args, 'func'):
            print('Missing subcommand. Use --help', file=sys.stderr)
            sys.exit(1)
        args.func(args)


def main():
    try:
        Uji().run(sys.argv[1:])
    except YamlError as e:
        logger.critical(f'Failed to parse YAML file: {e}')


if __name__ == '__main__':
    main()
