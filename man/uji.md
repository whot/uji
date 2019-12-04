% UJI(1)

NAME
====

uji - Test case log creation and manipulation tool

SYNOPSIS
========

**uji new source.yaml [test-directory]**

DESCRIPTION
============

**uji** is a tool to create sets of test logs from predefined test cases.
**uji** is not a test suite, it merely provides a repeatable scaffolding for
collecting and storing test results, log files and the output of test
commands.

**uji** parses source YAML files (see **SOURCE FILES**) and generates a
directory containing a template test log and a record of all tests to be
run. The user can then either edit that record directly or use the **uji**
commands to add logs and tick off test results.

All data is stored in git. **uji** expects to be run within a git directory.

OPTIONS
=======

**-h**, **\-\-help**
: Display a help message

**\-\-verbose**
: Verbose output, primarily for debugging

uji new
-------

**source.yaml**
: Specifies the YAML file to look up for test cases. Any files referenced by
this YAML file must live in the same directory as that file.

**test-directory**
: Optional output directory. Where omitted, **uji** creates a unique
directory name based on the source file.

