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

import cmd
import click
import collections
import logging
import io
import yaml
import re
import time
import sys
import git
import os
import shutil
from copy import deepcopy
from pathlib import Path

from collections import UserDict


class ColorFormatter(logging.Formatter):
    BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, LIGHT_GRAY = range(30, 38)
    DARK_GRAY, LIGHT_RED, LIGHT_GREEN, LIGHT_YELLOW, LIGHT_BLUE, LIGHT_MAGENTA, LIGHT_CYAN, WHITE = range(90, 98)
    COLORS = {
        'WARNING': LIGHT_RED,
        'INFO': LIGHT_GREEN,
        'DEBUG': LIGHT_GRAY,
        'CRITICAL': YELLOW,
        'ERROR': RED,
    }
    RESET_SEQ = '\033[0m'
    COLOR_SEQ = '\033[%dm'
    BOLD_SEQ = '\033[1m'

    def __init__(self, *args, **kwargs):
        logging.Formatter.__init__(self, *args, **kwargs)

    def format(self, record):
        levelname = record.levelname
        color = self.COLOR_SEQ % (self.COLORS[levelname])
        message = logging.Formatter.format(self, record)
        message = message.replace('$RESET', self.RESET_SEQ)\
                         .replace('$BOLD', self.BOLD_SEQ)\
                         .replace('$COLOR', color)
        for k, v in self.COLORS.items():
            message = message.replace('$' + k, self.COLOR_SEQ % (v + 30))
        return message + self.RESET_SEQ


log_format = '$COLOR%(levelname)s: %(message)s'
logger_handler = logging.StreamHandler()
logger_handler.setFormatter(ColorFormatter(log_format))
logger = logging.getLogger('uji')
logger.addHandler(logger_handler)
logger.setLevel(logging.INFO)

def bold(text):
    return f'{ColorFormatter.BOLD_SEQ}{text}{ColorFormatter.RESET_SEQ}'


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


class MarkdownError(Exception):
    pass


class MarkdownParser(object):
    '''
    A minimal parser for markdown, custom-tailored to what we need in uji
    which is:
    - sections, because we need those for grouping
    - checkboxes, top-level only
    - paragraphs, anything else
    '''
    class Node(object):
        '''
        A single logical element.

        .. attribute:: lines

           The Lines attached to this node, excluding those attached to the
           children nodes.
        '''
        def __init__(self, line, parent=None):
            self.lines = []
            self.parent = None
            self.children = []
            self.type = None

        def add_child(self, child):
            child.parent = self
            self.children.append(child)

        @property
        def is_root(self):
            return False

        @property
        def text(self):
            return '\n'.join([l.text for l in self.lines])

    class Root(Node):
        def __init__(self):
            super().__init__(line=None)
            self.lines = None

        @property
        def is_root(self):
            return True

    class Paragraph(Node):
        '''
        The simplest node, basically anything that's not a section header
        or a top-level checkbox.
        '''
        def __init__(self, line, parent=None):
            super().__init__(line, parent)
            self.indent = 0
            self.type = 'paragraph'

        @classmethod
        def handle_lines(cls, lines, node, section):
            line = lines[0]
            if not line.text:
                return None, [line], lines[1:]

            match = re.match(r'(\s*)(.*)', line.text)
            if match[1]:
                # some indent, let's append it to the current paragraph (if
                # any) or as a new paraph to the current node.
                # This works because we only care about top-level
                # checkboxes in uji.
                if isinstance(node, MarkdownParser.Paragraph):
                    logger.debug('Extension of current paragraph')
                    return node, [line], lines[1:]

                p = cls(line, node)
                p.indent = len(match[1])
                node.add_child(p)
                logger.debug(f'Sub-paragraph for {node}')
            else:
                # no indent, belongs to current section
                if (isinstance(node, MarkdownParser.Paragraph) and
                        node.indent == 0):
                    logger.debug('Extension of paragraph')
                    return node, [line], lines[1:]


                if section is None:
                    section = node  # should be the root node
                p = cls(line, section)
                section.add_child(p)
                logger.debug(f'Top-level paragraph for {section}')

            return p, [line], lines[1:]

    class Checkbox(Node):
        def __init__(self, line, parent=None):
            super().__init__(line, parent)
            self.type = 'checkbox'

        @classmethod
        def from_lines(cls, lines, section):
            line = lines[0]
            match = re.match(r'^- \[[ xX]\] (.*)', line.text)
            if not match:
                return None, [], lines

            line = lines[0]
            cb = cls(line, section)
            if section:
                section.add_child(cb)
            return cb, [line], lines[1:]

        @property
        def checked(self):
            return self.text[3] != ' '

        @checked.setter
        def checked(self, value):
            match = re.match(r'^- \[[ xX]\] (.*)', self.text)
            assert match is not None
            x = 'x' if value else ' '
            self.lines[0].text = f'- [{x}] {match[1]}'

        @property
        def link(self):
            match = re.match(r'.* \[(.*)\]\((.*)\).*', self.text)
            if not match:
                return None, None

            filename = re.sub(r'`?([^`]*)`?', r'\1', match[1])
            path = match[2]
            return filename, path


    class Section(Node):
        def __init__(self, line, parent=None):
            super().__init__(line)
            self.headline = line.text
            self.marker = None
            self.parent = None
            self.type = 'section'

        @classmethod
        def from_lines(cls, lines, last_section):
            line = lines[0]
            section = cls(line)

            # header style ## foo
            match = re.match('^(#+) (.*)', line.text)
            if match:
                used = 1
                section.level = len(match[1])
                section.marker = match[1]
                section.headline = match[2]

                parent = last_section
                while parent and not parent.is_root:
                    if section.level > parent.level:
                        parent.add_child(section)
                        break
                    else:
                        parent = parent.parent
            else:
                # header style
                #   foo
                #   ===
                # at least 3 characters but strict underlining is not
                # required
                twolines = '\n'.join([l.text for l in lines[:2]])
                match = re.match('^(.*)\n([-_=.:]{3,})', twolines)
                if not match:
                    return None, [], lines

                used = 2
                section.headline = match[1]
                section.marker = match[2][0]
                # annoying: markdown doesn't specify which header style
                # is h1, h2, etc. So the only way we can know is by
                # running up the tree, if we have the same there it'll
                # be a sibling.
                parent = last_section
                while parent and not parent.is_root:
                    if parent.marker == section.marker:  # found a sibling
                        if parent.parent:
                            parent.parent.add_child(section)
                            section.level = parent.level
                        else:  # top-level section
                            section.level = 1
                        break
                    else:
                        # Need to search all parents for a matching
                        # underline
                        parent = parent.parent
                else:
                    # we couldnt't find a parent with the same underlining,
                    # so we have no siblings. This is either a top-level
                    # section or a level below our current parent
                    if last_section:
                        last_section.add_child(section)
                        section.level = last_section.level + 1
                    else:
                        section.level = 1

            logger.debug(repr(section))
            return section, lines[:used], lines[used:]

        def __str__(self):
            return self.headline

        def __repr__(self):
            return f'Section lvl {self.level}: "{self.text}", parent {self.parent if self.parent else "<none>"}'

    class Line(object):
        def __init__(self, lineno, text):
            text = text.replace('\n', '')
            self.lineno = lineno
            self.text = text
            self.section = None
            self.is_attachment = '📎' in text

        def __str__(self):
            return self.text

        def __repr__(self):
            return f'{self.lineno}: {self.text}'

        @property
        def attachment(self):
            '''Returns a tuple of (filename, path)'''
            match = re.match(r'.*📎 \[`(.*)`\]\((.*)\).*', self.text)
            return (match[1], match[2])

    def __init__(self, fd):
        self.lines = [MarkdownParser.Line(lineno, text) for (lineno, text) in enumerate(fd.readlines())]
        if not self.lines:
            raise MarkdownError('Empty markdown file')
        self.tree = self._parse(self.lines)

    def _parse(self, lines):
        tree = MarkdownParser.Root()

        logger.debug('Parsing markdown file')

        node = tree     # Current node
        section = None  # Current section

        while lines:
            logger.debug(lines[0])
            new_section, used, remainder = MarkdownParser.Section.from_lines(lines, last_section=section)
            if new_section:
                logger.debug(f'Found section {new_section}')
                section = new_section
                node = section
                if not new_section.parent:
                    tree.add_child(section)
            else:
                cb, used, remainder = MarkdownParser.Checkbox.from_lines(lines, section=section)
                if cb:
                    logger.debug('Found checkbox')
                    node = cb
                    if not cb.parent:
                        tree.add_child(cb)
                else:
                    p, used, remainder = MarkdownParser.Paragraph.handle_lines(lines, node, section)
                    if p:
                        node = p

            for l in used:
                l.section = section

            node.lines += used
            lines = remainder

        return tree

    @classmethod
    def from_file(self, filename):
        with open(filename) as fd:
            return MarkdownParser(fd)

    @classmethod
    def from_text(self, text):
        return MarkdownParser(io.StringIO(text))


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

    def br(self):
        self.fprint('')

    def h1(self, text):
        self.fprint(text)
        self.fprint('=' * len(text))

    def h2(self, text):
        self.fprint(text)
        self.fprint('-' * len(text))

    def h3(self, text):
        self.fprint(f'### {text}')

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
            self.parent.fprint(f'{spaces}- [ ] {text}')

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
                if test.description:
                    self.fmt.br()
                    self.fmt.h3(test.name)
                    self.fmt.p(test.description)
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


class UjiTest(cmd.Cmd):
    prompt = '(uji) '

    def __init__(self, directory):
        super().__init__()

        try:
            self.repo = git.Repo(search_parent_directories=True)
        except git.exc.InvalidGitRepositoryError:
            logger.critical('uji must be run from within a git tree')
            sys.exit(1)

        mds = Path(directory).glob('*.md')
        if not mds:
            raise ValueError(f'Cannot find a markdown file in {directory}')
        else:
            md = next(mds)
            try:
                next(mds)
                logger.warning('Multiple markdown files found, using "{md}"')
            except StopIteration:
                pass

        self.mdfile = md
        self.parser = MarkdownParser.from_file(md)

        uji_section = [s for s in self.parser.tree.children if s.type == 'section' and s.headline == 'Uji']
        if not uji_section:
            raise ValueError('Unable to find top-level section "Uji" in the markdown file')
        elif len(uji_section) != 1:
            logger.warning('Multiple "Uji" sectionis found, using the first one')
        uji_section = uji_section[0]

        self.sections = collections.OrderedDict()
        idx = 0
        for section in uji_section.children:
            if not section.type == 'section':
                continue

            tests = self._compile_tests(section)
            if tests:  # skip over sections without tests
                self.sections[idx] = section
                section.section_idx = idx
                idx += 1

        # for simplicity, select first test of first section
        self.section = self.sections[0]  # the currently selected test
        self.tests = self._compile_tests(self.section)
        self.test = self.tests[0]  # the currently selected test
        self.do_sections()

        self.dirty = False  # Writeout needed?

    def _compile_tests(self, section):
        tests = collections.OrderedDict()

        def find_tests(section, tests, idx=0):
            for cb in section.children:
                if not cb.type == 'checkbox':
                    continue

                tests[idx] = cb
                cb.test_idx = idx
                idx += 1
            return idx

        # FIXME: This currently goes two sections deep, anything below h3
        # won't be picked up. Needs to be addressed once the markdown file
        # format has been sorted out.
        idx = find_tests(section, tests)
        for subsection in section.children:
            idx = find_tests(subsection, tests, idx)

        return tests

    def do_exit(self, args):
        '''Exit uji'''
        print('bye')
        return True

    def do_quit(self, args):
        '''Exit uji'''
        return self.do_exit(args)

    def do_diff(self, args=None):
        '''
        Usage: diff [md]

        Show currently staged changes. If the literal 'md' is given,
        only the changes to the Markdown file are shown.
        '''

        if args == 'md':
            print(self.repo.git.diff('HEAD', '--staged', self.mdfile))
        else:
            print(self.repo.git.diff('HEAD', ['--staged']))

    def do_commit(self, args):
        '''
        Usage: commit "the commit message"

        Commit current changes to git. Where a message is given, that is
        used as commit message, otherwise some autogenerated message is
        created.
        '''
        # FIXME:
        pass

    def do_sections(self, args=None):
        '''List the sections in the file'''

        for idx, s in self.sections.items():
            print(f'[{idx}] {s.headline}')
        print(f'Current section is: [{self.section.section_idx}] {self.section}')
        print(f'Switch to section N with "s N"')


    def do_section(self, args):
        '''
        Usage: section N

        Where N is the section number as listed by the 'sections' command.
        '''
        try:
            self.section = self.sections[int(args)]
        except (KeyError, ValueError):
            print('Usage: section N where N is the index of the section')
            return

        self.tests = self._compile_tests(self.section)
        self.do_tests()

    def do_tests(self, args=None):
        '''
        Usage: tests

        Lists the tests of the currently selected section.
        '''
        print(f'{bold(self.section)}')
        print('')
        for p in self.section.children:
            if p.type != 'paragraph':
                break
            print(p.text)

        print(f'Tests available:')
        for idx, t in self.tests.items():
            print(f'[{idx}] {t.text}')
        print(f'Switch to test N with "t N"')

    def do_test(self, args=None):
        '''
        Usage: test N

        Where N is the test index as listed by the 'tests' command
        '''
        if args is not None:
            try:
                self.test = self.tests[int(args)]
            except (KeyError, ValueError):
                print('Usage: test N where N is the index of the test')
                return

        print(f'{bold("Current test:")}')
        print(f'  {self.test.text}')
        print(f'Use "x" to mark as done')
        if "📎" in self.test.text:
            print(f'Use "u" to upload the file and mark as done')
            print(f'Use "upload /path/to/file" to upload a custom file and mark as done')

    def do_upload(self, args):
        '''
        Usage: upload [/path/to/file]

        Upload the file to the uji test directory. If no filename is given,
        the filename from the markdown file is used.
        '''

        filename, path = self.test.link
        if not filename:
            logger.error('Cannot upload for current test')
            return

        if args:
            filename = args

        try:
            shutil.copyfile(filename, path)
            self.repo.index.add([os.fspath(path)])
            if args:
                logger.info(f'Copied "{args}" as {filename}')
            else:
                logger.info(f'Copied {filename} from localhost')
            self.do_mark()
        except Exception as e:
            logger.error(f'Failed to copy {filename}: {e}')
            self.do_test()

    def do_mark(self, args=None):
        '''
        Usage: mark

        Mark the currently selected tests as done
        '''
        self.test.checked = True
        self.dirty = True
        self.do_next()

    def do_unmark(self, args=None):
        '''
        Usage: unmark

        Unmark the currently selected test again
        '''
        self.test.checked = False
        self.dirty = True
        self.do_next()

    def do_next(self, args=None):
        '''
        Usage: next

        Select the next test
        '''
        try:
            self.test = self.tests[self.test.test_idx + 1]
        except KeyError:
            logger.warning('Already on the last test')
        self.do_test()

    def default(self, line):
        '''Fallback for any unrecognized commands'''

        aliases = {
                'n': self.do_next,
                'q': self.do_quit,
                'ss': self.do_sections,
                's': self.do_section,
                'tt': self.do_tests,
                't': self.do_test,
                'u': self.do_upload,
                'x': self.do_mark,
                'EOF': self.do_exit,
        }

        cmd, arg, line = self.parseline(line)
        try:
            func = aliases[cmd]
        except KeyError:
            pass
        else:
            return func(arg)

        super().default(line)

    def postcmd(self, stop, line):
        if self.dirty:
            self.dirty = False
            with open(self.mdfile, 'w') as fd:
                fd.write('\n'.join([l.text for l in self.parser.lines]))
            self.repo.index.add([os.fspath(self.mdfile)])

        return stop

    def run(self):
        self.cmdloop()


##########################################
#               The CLI interface        #
##########################################

# top-level command
@click.group()
@click.option('-v', '--verbose', count=True, help='increase verbosity')
@click.option('--quiet', 'verbose', flag_value=-1)
def uji(verbose):
    levels = {
        None: logging.INFO,
        1: logging.DEBUG,
        0: logging.INFO,
        -1: logging.ERROR,
    }

    logger.setLevel(levels.get(verbose, logging.DEBUG))
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


# subcommand: uji test
@uji.command()
@click.argument('directory',
                type=click.Path(file_okay=False, dir_okay=True, exists=True))
def test(directory):
    '''Update test logs in DIRECTORY'''
    try:
        UjiTest(directory).run()
    except MarkdownError as e:
        logger.criticial(f'Failed to parse markdown file: {e}')


def main(args=sys.argv):
    uji()


if __name__ == '__main__':
    main()
