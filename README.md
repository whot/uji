Uji - checklist generator and tracking system
=============================================

uji is a tool to generate checklists from template files and hold on to
those lists forever or until the cows come home, whichever happens later.

uji is useful for cases where a user has
- large checklists with overlapping items, e.g. the same sets of test to be
  performed on different hardware
- the checklists are recurring, e.g. they need to be performed on every
  package update
- not all checklist items will be ticked every time but the user needs to
  remember which ones were ticked off
- there is other free-form information to be stored alongside the
  checklists

The main purpose of uji is to simplify the answer to "Wait, didn't I test
this?"

- uji is not a todo list
- uji is not a test suite
- uji is not something you can integrate into a CI

If you have a test that can be automated, uji is not the right tool. uji
is to track manual tests that cannot be automated. If you want to generate
test summaries, uji is not the right tool. uji tracks **manual** tests.

uji is optimized for writing, not reading. 99% of the logs tracked with uji
will never be read. Hence uji is built for minimal friction to write the
tests - basically you need git, python and an editor. The central file is
a markdown text file that you can edit and annotate (almost) at will.
It's all stored in git, so backup, sharing, and collaboration is trivial.
It's markdown, so you push the file anywhere (gitlab, github, ...) and it'll
probably look nice in the browser.

uji just preps the file for you and (in the future) provides a set of
CLI tools to automate some tasks around maintaining the test files.

"uji" is Indonesian for "test".

Use case
========

Upgrading software packages usually requires multiple manual tests. Ideally
you have a checklist to tick off the things you tested. Next time you
upgrade that same package, the same checklist applies. Ideally you tick off
all the checklist items every time but we both know you don't. Maybe
hardware is missing, or the moon phase is wrong for tedious work, or, well,
so many reasons.

And then suddenly, a few months later a bug reports appears. And now the
question is: "wait, didn't I test this?"

And uji should be able answer that question.

How it works
============

The core of uji is a set of test templates in YAML format. These templates
are combined to a full test document (in markdown) on invoking `uji new`.
That file together with the log files required for the various tests are
stored in a git tree. As the tests are performed the user ticks them off in
the .md file and eventually commits them to git.

The next test run does the same, `uji new` creates a new directory, rinse,
wash, repeat.

So when the question "did I test this?" arises, you can go back, check the
respective log set and check - is the box for that test ticked off?
And if it is and it's still broken - well, you should have the various log
files in that same directory to figure out where the differences are.

None of this is novel of course, uji is just a commandline wrapper to make
that proces simpler.

Usage
=====

Look at the [example.yaml](example.yaml) file for an example test
configuration.

```
$ mkdir my-test-results && cd my-test-results
$ git init
$ wget -o mypackage.yaml https://raw.githubusercontent.com/whot/uji/master/examples/example.yaml
```

Now you're set up. Edit the `mypackage.yaml` file and add your tests.
Once ready, `git commit mypackage.yaml` because you want this to be
preserved.

And when you're ready to start a test run:

```
$ cd my-test-results
$ uji new mypackage.yaml
Your test records and log files are
  mypackage-2019-12-10.0/
  mypackage-2019-12-10.0/logitech_keyboard
  mypackage-2019-12-10.0/t450_keyboard
  mypackage-2019-12-10.0/t460_keyboard
  mypackage-2019-12-10.0/example.md
  mypackage-2019-12-10.0/example.yaml
  mypackage-2019-12-10.0/logitech_g500s
  mypackage-2019-12-10.0/macbook_keyboard
  mypackage-2019-12-10.0/logitech_mx_anywhere_2s
  mypackage-2019-12-10.0/logitech_keyboard/test_hotplug_libinput
  mypackage-2019-12-10.0/logitech_keyboard/test_usb_logs
  mypackage-2019-12-10.0/logitech_keyboard/log_input_devices
  mypackage-2019-12-10.0/logitech_keyboard/test_hotplug_libinput/dmesg
  mypackage-2019-12-10.0/logitech_keyboard/test_usb_logs/lsusb −v
  mypackage-2019-12-10.0/logitech_keyboard/log_input_devices/libinput record −−all
  mypackage-2019-12-10.0/logitech_keyboard/log_input_devices/∕proc∕bus∕input∕devices
  mypackage-2019-12-10.0/t450_keyboard/log_input_devices
  mypackage-2019-12-10.0/t450_keyboard/log_input_devices/libinput record −−all
  mypackage-2019-12-10.0/t450_keyboard/log_input_devices/∕proc∕bus∕input∕devices
  mypackage-2019-12-10.0/t460_keyboard/log_input_devices
  mypackage-2019-12-10.0/t460_keyboard/log_input_devices/libinput record −−all
  mypackage-2019-12-10.0/t460_keyboard/log_input_devices/∕proc∕bus∕input∕devices
  mypackage-2019-12-10.0/logitech_g500s/log_input_devices
  mypackage-2019-12-10.0/logitech_g500s/log_input_devices/libinput record −−all
  mypackage-2019-12-10.0/logitech_g500s/log_input_devices/∕proc∕bus∕input∕devices
  mypackage-2019-12-10.0/macbook_keyboard/test_usb_logs
  mypackage-2019-12-10.0/macbook_keyboard/log_input_devices
  mypackage-2019-12-10.0/macbook_keyboard/test_usb_logs/lsusb −v
  mypackage-2019-12-10.0/macbook_keyboard/log_input_devices/libinput record −−all
  mypackage-2019-12-10.0/macbook_keyboard/log_input_devices/∕proc∕bus∕input∕devices
  mypackage-2019-12-10.0/logitech_mx_anywhere_2s/log_input_devices
  mypackage-2019-12-10.0/logitech_mx_anywhere_2s/log_input_devices/libinput record −−all
  mypackage-2019-12-10.0/logitech_mx_anywhere_2s/log_input_devices/∕proc∕bus∕input∕devices
Run "git commit" to commit the changes, or "git reset" to throw them away
$ git commit -am 'mypackage: new test log set'
$ vim mypackage-2019-12-04.0/mypackage.md
# tick off the tests as you confirm them

$ cp /proc/bus/input/devices mypackage-2019-12-10.0/logitech_keyboard/log_input_devices/∕proc∕bus∕input∕devices
$ lsusb &> mypackage-2019-12-10.0/macbook_keyboard/test_usb_logs/lsusb −v

# copy the other files into the right file names

$ git commit -am 'mypackage: test log set done'
```

And that's it for now.

License
=======

uji is licensed under the MIT license. See LICENSE for more info.
