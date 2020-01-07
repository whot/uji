.. _use-cases:

Example use case
----------------

Imagine a software release or update that requires a number of manual tests
to completion. Such a checklist could look like this::

    AMD
    - check suspend/resume
    - check GL rendering

    NVIDIA
    - check suspend/resume
    - check GL rendering
    - check installation/deinstallation of binary driver

    INTEL
    - check suspend/resume
    - check GL rendering

    MGA
    - check display lights up on MGA card

This checklist has some specific properties:

- **most** of the tests must be run on multiple hardware entities
- the tests can be divided up in to sets and each hw will run some sets
- a single person is unlikely to be able to test all of them in one go
- it may not be possible to tick off all items every time
- this checklist will basically be the same one next time

.. note:: New tests may be added in the future or existing tests may change,
          but that must not affect previously stored test results


**uji** provides the tools to generate this checklist and to track the
completion.

Initial setup
=============

The **intial setup** requires that

- the developer creates a ``test-results`` git repository (or whatever name
  you want to use)
- the developer writes the test sets and stores those in the git tree

The ``uji setup`` tool provides the required scaffolding to initialize a git
repository.

This initial setup must be performed once per test collection. **uji**
merely operates with markdown files and the yaml templates, it is up to the
developer to decide how to collate the results. One git repository per
package or one git repository for all packages, **uji** doesn't care.


Workflow
========

The workflow for a software release looks like this:

#. ``uji new`` creates a new checklist from the templates and commits it to git
#. log into the first test host (e.g. the AMD one)

   - ``git clone`` the ``test-results`` repository
   - Use ``uji view`` to tick off items and/or upload files
   - Use ``$EDITOR``, ``git commit`` to make manual annotations or other changes
   - ``git push`` the changes upstream

#. repeat for every host

.. note:: The use of ``uji view`` is optional, you can edit the markdown
          directly.

The idea is that a **new checklist is generated** for each
software update, then the items are ticked off one-by-one as the hw is
available and the test is completed. Since the data is in markdown and
stored in git, it is trivial to clone the results to the target host, edit
it there and then push it back up.

Five months later, when a bug is reported, the developer can go back and
check whether that test was recorded with that software version.
