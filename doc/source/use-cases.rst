.. _use-cases:

Example use case
----------------

Imagine a software release or update that requires a number of manual tests
to completion. Such a todo list could look like this::

    AMD
    - check suspend/resume
    - check GL rendering

    NVIDIA
    - check suspend/resume
    - check GL rendering
    - check installation/deinstallation of binary driver

    INTEL
    - check suspend/resume on Intel card
    - check GL rendering on Intel card

    MGA
    - check display lights up on MGA card

This todo list has some specific properties:

- **most** of the tests must be run on multiple hardware entities
- the tests can be divided up in to sets and each hw will run some sets
- a single person is unlikely to be able to test all of them in one go
- it may not be possible to tick off all items every time
- this list will be the same every time (though it may of course grow)


**uji** provides the tools to generate this todo list and to track the
completion. The intial setup requires that

- the developer creates a ``test-results`` git repository
- the developer writes the test sets and stores those in the git tree

The workflow for a software release looks like this:

- create a new todo list with ``uji new`` and ``git commit`` that empty todo list
- log into the first test host (e.g. the AMD one)

  - ``git clone`` the ``test-results`` repository
  - Use ``uji view``, then ``git commit`` and ``git push`` those changes

- log into the second test host (e.g. the NVIDIA one)

  - ``git clone`` the ``test-results`` repository
  - Use ``uji view``, then ``git commit`` and ``git push`` those changes

- repeat for every host

.. note:: The use of ``uji view`` is optional, you can edit the markdown
          directly.

The idea is that a **new todo list is generated** for each
software update, then the items are ticked off one-by-one as the hw is
available and the test is completed. Since the data is in markdown and
stored in git, it is trivial to clone the results to the target host, edit
it there and then push it back up.

Five months later, when a bug is reported, the developer can go back and
check whether that test was recorded with that software version.
