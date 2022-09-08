Runltp-ng
=========

LTP Next-Gen runner is a new version of the `runltp` script used by the
[Linux Test Project](https://github.com/linux-test-project/ltp).

    Host information

        System: Linux
        Node: susy
        Kernel Release: 5.14.21-150400.24.21-default
        Kernel Version: #1 SMP PREEMPT_DYNAMIC Wed Sep 7 06:51:18 UTC 2022 (974d0aa)
        Machine Architecture: x86_64
        Processor: x86_64

        Temporary directory: /tmp/runltp.acer/tmp3t9hwivz

    Connecting to SUT: host
    Downloading suite: math
    Starting suite: math
    abs01: pass
    atof01: pass
    float_bessel: pass
    float_exp_log: pass
    float_iperb: pass
    float_power: pass
    float_trigo: pass
    fptest01: pass
    fptest02: pass
    nextafter01: pass

    Suite Name: math
    Total Run: 10
    Elapsed Time: 4.2 seconds
    Passed Tests: 22
    Failed Tests: 0
    Skipped Tests: 0
    Broken Tests: 0
    Warnings: 0
    Kernel Version: Linux 5.14.21-150400.24.21-default #1 SMP PREEMPT_DYNAMIC Wed Sep 7 06:51:18 UTC 2022 (974d0aa)
    CPU: x86_64
    Machine Architecture: x86_64
    RAM: 15569568 kB
    Swap memory: 2095424 kB
    Distro: opensuse-leap
    Distro Version: 15.4


    Disconnecting from SUT: host


Quickstart
==========

Some basic commands are the following:

    # run syscalls and dio testing suites on host
    ./runltp-ng --run-suite syscalls dio

    # run syscalls and dio testing suites in qemu VM
    ./runltp-ng --sut=qemu:image=folder/image.qcow2 \
        --run-suite syscalls dio

    # run syscalls and dio testing suites via SSH
    # NOTE: paramiko and scp packages must be installed in the system
    ./runltp-ng --sut=ssh:host=myhost.com:user=root:key_file=myhost_id_rsa \
        --run-suite syscalls dio

It's possible to run a single command before running testing suites using
`--run-cmd` option as following:

    runltp-ng --run-cmd=/mnt/testcases/kernel/systemcalls/bpf/bpf_prog02 \
        --sut=qemu:image=folder/image.qcow2 \
        --run-suite syscalls dio

It can be used also to run a single command without running testing suites:

    runltp-ng --run-cmd=/mnt/testcases/kernel/systemcalls/bpf/bpf_prog02 \
        --sut=qemu:image=folder/image.qcow2

Every session has a temporary directory which can be found in
`/<TMPDIR>/runltp-of<username>`. Inside this folder there's a symlink
called `latest`, pointing to the latest session's temporary directory, and the
application will rotate over 5 sessions.

Setting up console for Qemu
===========================

To enable console on a tty device for a VM do:

* open /etc/default/grub
* add `console=$tty_name, console=tty0` to `GRUB_CMDLINE_LINUX`
* run grub-mkconfig -o /boot/grub/grub.cfg

Where `$tty_name` should be `ttyS0`, unless virtio serial type is used (i.e.
if you set the `serial=virtio` backend option, then use `hvc0`)

Development
===========

The application is validated using `pytest` and `pylint`.
To run unittests:

    pytest

To run linting checks:

    pylint --rcfile=pylint.ini ./ltp
