% UJI(1)

NAME
====

uji - Checklist creation and tracking tool

SYNOPSIS
========

**uji** \<command\>

**uji setup** _project-directory_

**uji new** _source.yaml_ [_directory_]

**uji view** _directory_

**uji check** _directory_

DESCRIPTION
============

**uji** is a tool to create checklists from predefined templates and tracks
the state of those checklists via git.
**uji** is not a test suite, it merely provides a repeatable scaffolding for
creating and storing checklists, log files and the output of various
commands.

**uji** parses source YAML files (see **SOURCE FILES**) and generates a
directory containing a template test log and a record of all tests to be
run. The user can then either edit that record directly or use the **uji**
commands to add logs and tick off test results.

All data is stored in git. **uji** expects to be run within a git directory
and will commit any changes to git immediately.

OPTIONS
=======

**-h**, **\-\-help**
: Display a help message

**\-\-verbose**
: Verbose output, primarily for debugging

COMMANDS
========

uji setup *project-directory*
-----------------------------

Set up *project-directory* to track future checklists. This creates the
given directory, initializes it as git repository and fills it with example
templates.

uji new *source.yaml* *[directory]*
---------------------------------------------

This command should be run from within the *project-directory* created by
**uji setup**.

Creates a new *directory* containing a markdown file that is the checklist
to be tracked. Where the checklist contains files to record, empty template
files are generated for those. The new test directory and any template files
are committed to git.

The checklist is generated based on the *source.yaml* file. Where
*directory* is omitted, **uji new** creates a unique directory name based on
the source file and a timestamp.

uji view *directory*
---------------------

This command should be run from within the *project-directory* created by
**uji setup** with a *directory* created by **uji new**.

The command **uji view** opens an interactive viewer for the **uji**
markdown file in the given directory. Use this viewer to quickly tick off
checkboxes and upload files.

Keyboard shortcuts:

*\<down\>* or *j*, *\<up\>* or *k*
: move cursor one line down or up

*\<Esc\>*, *q*
: quit

*\<Space\>*
: scroll one page down

*n*, *p*
: jump to next/previous checkbox

*u*
: upload the given file from the local host

*e*
: open **$EDITOR** to edit the markdown file directly

*f*
: toggle filename view

uji check *directory*
---------------------

**uji check** executes the file *uji-check* within the given *directory*.
This file is created by **uji new** and may contain various checks you need
to run before actually testing. For example, you may want to put a kernel
version check to ensure **uji** test runs are run on the correct machines.

The exit status of *uji-check* determines whether **uji check** succeeds.

**uji check** is automatically run by **uji view** on startup.


SEE ALSO
========

git(1)
