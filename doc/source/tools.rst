.. _uji-setup:

uji setup
=========

``uji setup`` is the tool to set up a directory for keeping **uji** test logs
and test cases. This tool only needs to run once per project. It creates the
directory, copies a stub ``README.md`` and an example ``yaml`` file into
place.

::

  $ uji setup myproject
  ...
  $ tree myproject
  ├── myproject.yaml
  └── README.md
  └── .git
  $ cd myproject
  $ git log
  commit 82636a681bb02d51e281a49194c99be7d3e6ab10 (HEAD -> master)
  Author: Author Name <your.name@email.com>
  Date:   Fri Dec 13 15:41:52 2019 +1000

        Initial setup for myproject

  
Once complete, look at the ``myproject.yaml`` file in that directory and
modify it. By default, it is based off the ``examples.yaml`` in the **uji**
upstream git directory.

If you plan to have multiple projects' test reports in the same directory,
we recommend that the YAML files are placed in a ``templates/`` folder.

.. _uji-new:

uji new
=======

``uji new`` is the tool to create a new test run. This must be run within a
**uji** directory (see :ref:`uji-setup`).

::

  $ cd myproject
  $ uji new myproject.yaml myproject-v1.0.9
  ....
  $ tree myproject-v1.0.9
  myproject-v1.0.9
  ├── myproject.md
  ├── myproject.yaml
  ├── keyboard
  │   └── test_system
  │       └── dmesg
  └── mouse
      └── test_system
          └── dmesg

As you can see above, the directory contains the compiled YAML file and a
markdown file that contains the actual test logs. Where the test calls for
files to be attached, these are generated as empty files in a directory
structure that resembles the actors and tests specified in the test
templates. This allows you to attach multiple versions of the same file
(``dmesg`` in the example above) to a test log.

The second argument to ``uji new`` is optional, if missing **uji** will
generate a folder using the current date (e.g. ``myproject-20191224.0``).

``uji new`` commits that new directory to the git tree, so you will be ready
to go immediately.

.. _uji-view:

uji view
========

**uji view** is an interactive markdown viewer with the functionality to
make checklists easy to handle.

::

  $ cd myproject
  $ uji view myproject-v1.0.9


Within this viewer, you have several keyboard shortcuts:

- ``<Esc>``, ``q`` - quit and git commit any changes
- ``<down>``, ``j`` - move the cursor down one line
- ``<up>``, ``k`` - move the cursor up one line
- ``<space>`` - move view down one page
- ``n`` - jump to next line with a checkbox
- ``p`` - jump to previous line with a checkbox
- ``t`` - toggle checkbox on/off
- ``e`` - start editor (requires ``$EDITOR`` to be set)
- ``u`` - upload the given file. For checkboxes that take an attachment,
  this copies the filename given from the local host into the right
  directory and toggles the checkbox to on.
- ``f`` - toggle filename view between filename and target path. Use this to
  see the file path a given log file needs to be copied to.


