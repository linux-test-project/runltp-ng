Runltp-ng
=========

LTP Next-Gen runner is a new version of the `runltp` script used by the
[Linux Test Project](https://github.com/linux-test-project/ltp).

Quickstart
==========

Some basic commands are the following:

    # run syscalls and dio testing suites on host
    ./runltp-ng --run-suite syscalls dio

    # run syscalls and dio testing suites in qemu VM
    ./runltp-ng --sut=qemu:image=folder/image.qcow2 \
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

Development
===========

The application is validated using `pytest` and `pylint`.
To run unittests:

    pytest

To run linting checks:

    pylint --rcfile=pylint.ini ./ltp
