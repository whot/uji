.. _quickstart:

Quickstart
----------

Install uji::

  pip install --user uji

Set up the first checklist with a test template from the examples::

  uji setup my-test-results
  cd my-test-results
  uji new mypackage.yaml
  git commit -m 'mypackage checklist'

Work on the checklist::

  uji view mypackage-*/
  git commit -m 'updated tests'
