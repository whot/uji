Uji
===

This is an example markdown file as should be produced by uji new. The
point of this is a guide for developing uji. Expect this to change.

The markdown file, once produced, is largely free-form. However, uji test
must be able to parse the file to automate some of the tasks, so some
structure is required.

uji test generally parses gitlab-compatible markdown.
There **must** be a top-level section named Uji. That is the only section
uji test looks at for data.

The content of this section is what is described in the section(s)
 `file:` of the yaml file(s).

Generic
-------

There is one section named 'Generic' for any tests that aren't filtered by
actor. Tests themselves are grouped: those that do not have a description
are assembled together first as one list. Otherwise, the order matches the
order in the yaml source files.

- [ ] a test case is prefixed with a checkbox
- [ ] a file [`/path/to/file`](link/to/uji/test/directory/file)

### Test name

A set of tests with a description is added as h3 section, with the test
description following the test name. Markdown like **bold** is supported.

- [ ] this is the actual test to run
- [ ] command [`lsusb`](link/to/uji/test/directory/lsusb)

### Other test name

Again, a set of tests with a description as h3 section. uji doesn't care
- whether
- you
- have
- a list here
or any other form or markup.

- [ ] the tests themselves must be checkboxes though
- [ ] file [`/path/to/file`](...)

Actor 1 name
------------

Actors translate into h2 sections. The actor description follows the section
header before any test cases. Really, same as Generic above, it's just a
fake actor added automatically.

Test cases are grouped in the same way too. Tests without description first:

- [ ] a test case is prefixed with a checkbox
- [ ] a file [`/path/to/file`](link/to/uji/test/directory/file)
 

### Custom test

Tests with description afterward

- [ ] tried turning it on and off again


Actor 2 name
------------

The tests are repeated by actor depending on the filters.

### Custom test

Tests with description afterward

- [ ] tried turning it on and off again

Other Notes
===========

Other sections in the markdown file are ignored by uji, so they are
completely free-form.
