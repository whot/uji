Installation
------------

**uji** shold be installed directly from git via pip::

  pip install --user git+https://github.com/whot/uji.git

Installation via pip is recommended as this will install all dependencies as
well.

**uji** can be run from a local git checkout, however note that **uji** will
assume it is run from the git tree with the test cases: ::

  git clone https://github.com/whot/uji
  cd /path/to/testcases
  /path/to/uji.git/uji.py [...]

Alternatively, to install a local git checkout: ::

  git clone https://github.com/whot/uji
  cd uji
  pip install --user .

**uji** is not yet available on PyPI.
