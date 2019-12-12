.. _quickstart:

Quickstart
----------

Install uji::

  pip install --user git+https://github.com/whot/uji.git

Set up the first todo list with a test template from the examples::

  uji setup my-test-results
  cd my-test-results
  uji new mypackage.yaml
  git commit -m 'mypackage todo list'

Work on the todo list::

  uji view mypackage-*/
  git commit -m 'updated tests'
