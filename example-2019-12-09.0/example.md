Uji
===

This is an example yaml file. The text here is used as the file
description in the generated markdown file.


Generic
-------
- [ ] hid-tools test suite
- [ ] kernel not tainted on boot
- [ ] [`/proc/bus/input/devices`](example-2019-12-09.0/generic.log_input_devices.∕proc∕bus∕input∕devices)
- [ ] [`evtest`](example-2019-12-09.0/generic.log_input_devices.evtest)
- [ ] `my-command --version`: `COMMAND OUTPUT`
- [ ] [`/path/to/testsuite.output`](example-2019-12-09.0/generic.log_some_check.∕path∕to∕testsuite.output)
- [ ] `some-command`
  - [ ] SUCCESS
  - [ ] FAIL
- [ ] `gnome-control-center`: <strong>ADD COMMENTS HERE</strong>
  - check scrolling works in the test area

AT Translated Keyboard
----------------------

the PS/2 thing with keys as found in laptops

- [ ] make sure we can type keys
- [ ] kbd LEDs
- [ ] unplugging shows `DEVICE_ADDED`/`DEVICE_REMOVED` events
- [ ] [`dmesg`](example-2019-12-09.0/generic_laptop_keyboard.test_hotplug.dmesg)
  - collect dmesg after plug/unplug

External USB Keyboard
---------------------

A USB keyboard

- [ ] make sure we can type keys
- [ ] kbd LEDs
- [ ] plug and unplug the keyboard
- [ ] unplugging shows `DEVICE_ADDED`/`DEVICE_REMOVED` events
- [ ] [`dmesg`](example-2019-12-09.0/generic_usb_keyboard.test_hotplug.dmesg)
  - collect dmesg after plug/unplug
- [ ] check lsusb after plugin
- [ ] [`lsusb -v`](example-2019-12-09.0/generic_usb_keyboard.test_usb_logs.lsusb −v)

AMD
---

### Normal suspend/resume test

This test checks behavior of a **normal** suspend/resume cycle.

Setup:
- suspend the machine
- resume the machine
Machine must be connected to power during this test.


- [ ] machine must not freeze or crash
- [ ] all monitors (including dock) turn back on on resume
- [ ] dmesg is free of obvious errors or warnings
- [ ] `dmesg`: `COMMAND OUTPUT`

### Video card hotplugging test

Setup:
- machine must be connected to power
- put on a rubber suit and rubber gloves
- rip the card out of the machine
- extinguish any fire caused by the sparks


- [ ] machine has shut down
- [ ] building is on fire


