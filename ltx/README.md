# Linux Test (Project) Executor

The `ltx` program runs on the system under test (SUT). It's primary
purpose is to run test executables in parallel and serialise the
results. It is a dumb program that executes simple commands sent to it
by a test scheduler (runltp-ng). The commands are encoded as
[MessagePack](https://github.com/msgpack/msgpack/blob/master/spec.md)
arrays as are the results.

The first element of the array is the message type, represented as an
integer. The rest of the array contents (if any) depend on the message
type.

In classic UNIX fashion, stdin and stdout are used to receive and send
commands. This makes LTX transport agnostic, a program such as
`socat`, `ssh` or just `sh` can be used to redirect the standard I/O
of LTX.

## Dependencies

LTX itself just needs Clang or GCC. The tests require Python 3.x with
pytest, msgpack and pexpect. Plus both Clang and GCC with support for
the address and undefined behavior sanitizers.

## Running

To run the tests use `pytest test.py`

## Architecture

LTX maintains a table of up to 128 process slots indexed from 0
to 127. Each slot contains some configuration data for running a
process and the process state (if any). Slots can be reused for
running processes in serial.

Using only 128 processes allows us to always use msgpack's fixint type
for the table id. If the SUT can handle more parallel processes than
this then multiple LTX instances can be created.

The following messages use the `table_id` to specify which slot is
being mutated or read from. For some messages the `table_id` could be
`nil` (distinct from a fixint value of 0) in which case the message is
not associated with a particular table entry.

### Timing

Many messages from the SUT contain nano second time stamps. These are
taken with `CLOCK_MONOTONIC_RAW` or `CLOCK_MONOTONIC`. See `man 2
clock_gettime`.

## Messages

LTX is not intended to have a generic MessagePack parser. There are
several ways in which a message can be encoded. However you can assume
LTX only accepts the shortest possible encoding.

All messages are wrapped in an fixarray. first element is the message
type which is a positive fixint.

LTX echos messages back to acknowledge them. The host should not echo
messages back to LTX.

So usually messages start like the following:

| fixarray enclosing msg | msg type fixint | table fixint            |
|:-----------------------|:----------------|:------------------------|
| `0x90`-`0x9f`          | `0x01`-`0x05`   | `0xc0` or `0x00`-`0x7f` |

Not all messages have a table field

### Ping

Sent to LTX which should respond with [Pong](#Pong).

`[0]`

### Pong

Response to [Ping](#Ping). Contains a nano second time stamp of when
Pong was sent.

`time`: uint 64

`[1, time]`

### Env

Sent to LTX to set an environment variable. If no table_id is
specified then it is set for ltx itself and all sub processes.

`table_id`: positive fixint | nil
`key`: fixstr | str 8
`value`: fixstr | str 8 | str 16

`[2, table_id, key, value]`

### Exec

Sent to LTX to execute a program. `pathname` is the absolute or
relative executable path. `argv1...argvn` are the arguments and can be
omitted. The value for `argv[0]` is extracted from `pathname`.

`table_id`: positive fixint
`pathname`: fixstr | str 8
`argv[1..12]`: fixstr | str 8

`[3, table_id, pathname, argv1, ..., argv12]`

### Log

Sent from LTX to the host to log child process output.

`table_id`: positive fixint | nil
`time`: uint 64
`text`: fixstr | str 8

`[4, table_id, time, text]`

### Result

Sent by LTX to the host to indicate the exit status of a process or
the signal which killed it. If it was a test process then the exit
status is the overall test result.

See `waitid`.

`table_id`:  positive fixint
`time`: uint 64
`si_code`: uint 8
`si_status`: uint 8

`[5, table_id, time, si_code, si_status]`

### Get File

Sent to LTX; starts a file transfer from LTX to the host. LTX will
respond with a single data message.

Note that this will block LTX while the transfer is in progress. Also
it's unclear what size of file this can handle.

`path`: fixstr | str 8

`[6, path]`

### Set File

Sent to LTX; will save the contained data to the path specified.

Not that like all messages this is echoed back. Also see Get File
above.

`path`: fixstr | str 8
`data`: bin 8 | bin 16 | bin 32

`[7, path, data]`

### Data

`data`: bin 8 | bin 16 | bin 32

`[8, data]`

### Kill

Sent to LTX; sends the kill signal to the process in the specified
table entry. If kill results in ESRCH the error is ignored

`table_id`: positive fixint

`[9, table_id]`

### Version

Sent to LTX; responds with a log message containing the version
e.g. "LTX Version=0.0.1-dev". Everything after the '=' is the version
number.

`[10]`
