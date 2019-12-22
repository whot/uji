Uji - a checklist tracker
=========================

**uji** is a tool to track the completion status of recurring checklists.
Specifically:

- it generates a (markdown) checklist from (yaml) templates
- it stores that checklist in git and thus tracks when and which items of
  that list you ticked off

This is particularly useful for situations where manual checks are required
as part of e.g. a software release or upgrade. As everything is stored in
git, it is possible to then later go back and verify whether the checklist
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
