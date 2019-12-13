Uji - a todo list tracker
=========================

**uji** is a tool to track the completion status of recurring todo lists.
Specifically:

- it generates a (markdown) todo list from (yaml) templates
- it stores that todo list in git and thus tracks when you check it off

This is particularly useful for situations where manual checks are required
as part of e.g. a software release or upgrade. As everything is stored in
git, it is possible to then later go back and verify whether the todo list
item was ticked off or not.

See :ref:`use-cases` for an extensive example use-case.

**uji** is the Indonesian word for "test".

Source
------

**uji** is available at
https://github.com/whot/uji

.. note:: **uji** requires Python 3.6 or later.


.. include:: installation.rst

License
-------

**uji** is available under the MIT license.

.. toctree::
   :hidden:
   :maxdepth: 4

   self
   use-cases
   installation
   quickstart
   tools
