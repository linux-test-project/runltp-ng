"""
Tests for LTX binary.
"""
import os
import re
import time
import pytest
import msgpack


class LTXHelper:
    """
    Helper class to send/receive message from LTX.
    """

    def __init__(self, proc) -> None:
        self._proc = proc
        self._buff = bytes()
        self._start_time = time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)

    @property
    def proc(self):
        """
        LTX subprocess.
        """
        return self._proc

    def read(self):
        """
        Read some data from stdout.
        """
        return os.read(self._proc.stdout.fileno(), 1 << 21)

    def expect_exact(self, data):
        """
        Expect for an exact message when reading from stdout.
        """
        length = len(data)

        while len(self._buff) < length:
            self._buff += self.read()

        for i in range(length):
            if self._buff[i] == data[i]:
                continue

            raise ValueError(
                f"Expected {hex(data[i])}, "
                f"but got {hex(self._buff[i])} at {i} in "
                f"'{self._buff.hex(' ')}' / {self._buff}")

        self._buff = self._buff[length:]

    def expect_n_bytes(self, n):
        """
        Read n bytes from stdout.
        """
        while len(self._buff) < n:
            self._buff += self.read()

        self._buff = self._buff[n:]

    def unpack_next(self):
        """
        Unpack the next package using msgpack.
        """
        unpacker = msgpack.Unpacker()
        msg = None

        unpacker.feed(self._buff)

        while not msg:
            try:
                msg = unpacker.unpack()
            except msgpack.OutOfData:
                data = self.read()
                self._buff += data
                unpacker.feed(data)

        self._buff = self._buff[unpacker.tell():]

        return msg

    def send(self, data):
        """
        Send some data to stdin.
        """
        assert os.write(self._proc.stdin.fileno(), data) == len(data)
        # echo
        self.expect_exact(data)

    def check_time(self, time_ns):
        """
        Check if the given time is inside bounds.
        """
        assert self._start_time < time_ns
        assert time_ns < time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)


@pytest.fixture
def ltx_helper(executor):
    """
    Helper object for LTX process.
    """
    yield LTXHelper(executor)


@pytest.mark.parametrize("tool", ["gcc", "clang"])
def test_compile(ltx_compile, tool):
    """
    Compile LTX using different tools.
    """
    ltx_compile(tool)


def test_version(ltx_helper):
    """
    Test VERSION command.
    """
    ltx_helper.send(msgpack.packb([10]))
    ver_msg = ltx_helper.unpack_next()

    assert len(ver_msg) == 4
    assert ver_msg[0] == 4
    assert ver_msg[1] is None

    assert re.match(r'LTX Version=0.0.1-dev', ver_msg[3]) is not None


def test_ping_nolib(ltx_helper):
    """
    Test PING without using msgpack.
    """
    # Ping: [0]
    ltx_helper.send(b'\x91\x00')
    # Pong: [1, time]
    ltx_helper.expect_exact(b'\x92\x01\xcf')
    ltx_helper.expect_n_bytes(8)


def test_ping(ltx_helper):
    """
    Test PING command.
    """
    # Ping
    ltx_helper.send(msgpack.packb([0]))
    # Pong
    pong = ltx_helper.unpack_next()
    assert len(pong) == 2
    assert pong[0] == 1

    ltx_helper.check_time(pong[1])


def test_ping_flood(ltx_helper):
    """
    Test multiple PING commands.
    """
    pings = msgpack.packb([[0] for _ in range(2048)])[3:]
    assert ltx_helper.proc.stdin.write(pings) == len(pings)

    ping_eg = msgpack.packb([0])
    pong_eg = msgpack.packb(
        [1, time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW)])

    for _ in range(2048):
        ltx_helper.expect_exact(ping_eg)
        ltx_helper.expect_exact(pong_eg[:-8])
        ltx_helper.expect_n_bytes(8)


def test_exec(ltx_helper, whereis):
    """
    Test EXEC command.
    """
    paths = whereis("uname")

    ltx_helper.send(msgpack.packb([3, 0, paths[0]]))
    log = ltx_helper.unpack_next()
    assert log[0] == 4
    assert log[1] == 0
    ltx_helper.check_time(log[2])
    assert log[3] == "Linux\n"

    res = ltx_helper.unpack_next()
    assert len(res) == 5
    assert res[0] == 5
    assert res[1] == 0
    ltx_helper.check_time(res[2])
    assert res[3] == 1
    assert res[4] == 0


def test_exec_echo(ltx_helper, whereis):
    """
    Test EXEC command echo.
    """
    paths = whereis("echo")

    ltx_helper.send(msgpack.packb(
        [3, 0, paths[0], "foo", "bar", "baz"]))
    log = ltx_helper.unpack_next()
    assert log[0] == 4
    assert log[1] == 0
    ltx_helper.check_time(log[2])
    assert log[3] == "foo bar baz\n"

    res = ltx_helper.unpack_next()
    assert len(res) == 5
    assert res[0] == 5
    assert res[1] == 0
    ltx_helper.check_time(res[2])
    assert res[3] == 1
    assert res[4] == 0


def test_set_file(ltx_helper, tmp_path):
    """
    Test SET_FILE command.
    """
    pattern = b'AaXa\x00\x01\x02Zz' * 2048
    d = tmp_path / 'get_file'
    d.mkdir()
    p = d / 'pattern'

    ltx_helper.send(msgpack.packb([7, p.as_posix(), pattern]))

    content = p.read_bytes()
    assert content == pattern

    ltx_helper.send(msgpack.packb([0]))
    assert ltx_helper.unpack_next()[0] == 1


def test_get_file(ltx_helper, tmp_path):
    """
    Test GET_FILE command.
    """
    pattern = b'AaXa\x00\x01\x02Zz' * 2048
    d = tmp_path / 'get_file'
    d.mkdir()
    p = d / 'pattern'

    p.write_bytes(pattern)
    ltx_helper.send(msgpack.packb([6, p.as_posix()]))

    data = ltx_helper.unpack_next()
    assert data[0] == 8
    assert data[1] == pattern


def test_kill(ltx_helper, whereis):
    """
    Test KILL command.
    """
    paths = whereis("sleep")

    ltx_helper.send(msgpack.packb([3, 1, paths[0], "10"]))
    time.sleep(0.1)
    ltx_helper.send(msgpack.packb([9, 1]))

    res = ltx_helper.unpack_next()
    assert res[0] == 5
    assert res[1] == 1
    ltx_helper.check_time(res[2])
    assert res[3] == 2
    assert res[4] == 9

def test_env(ltx_helper, whereis):
    """
    Test setting env variables
    """
    paths = whereis("printenv")

    ltx_helper.send(msgpack.packb([2, None, "LTPROOT", "/opt/ltp"]))
    ltx_helper.send(msgpack.packb([3, 1, paths[0], "LTPROOT"]))

    log = ltx_helper.unpack_next()
    assert log[0] == 4
    assert log[1] == 1
    assert log[3] == "/opt/ltp\n"
    res = ltx_helper.unpack_next()
    assert res[0] == 5
    assert res[3] == 1
    assert res[4] == 0

    ltx_helper.send(msgpack.packb([2, 1, "LTPROOT", "/usr/share/ltp"]))
    ltx_helper.send(msgpack.packb([3, 1, paths[0], "LTPROOT"]))

    log = ltx_helper.unpack_next()
    assert log[0] == 4
    assert log[3] == "/usr/share/ltp\n"
    res = ltx_helper.unpack_next()
    assert res[0] == 5
    assert res[3] == 1
    assert res[4] == 0

    ltx_helper.send(msgpack.packb([2, 1, "FOO", "bar"]))
    ltx_helper.send(msgpack.packb([3, 1, paths[0], "FOO"]))

    log = ltx_helper.unpack_next()
    assert log[0] == 4
    assert log[3] == "bar\n"
    res = ltx_helper.unpack_next()
    assert res[0] == 5
    assert res[3] == 1
    assert res[4] == 0

    ltx_helper.send(msgpack.packb([2, 1, "LTPROOT", "/mnt/ltp"]))
    ltx_helper.send(msgpack.packb([3, 1, paths[0], "LTPROOT"]))

    log = ltx_helper.unpack_next()
    assert log[0] == 4
    assert log[3] == "/mnt/ltp\n"
    res = ltx_helper.unpack_next()
    assert res[0] == 5
    assert res[3] == 1
    assert res[4] == 0

    ltx_helper.send(msgpack.packb([2, 1, "BAZ", "bar"]))
    ltx_helper.send(msgpack.packb([2, 1, "FOO", "foo-bar-baz"]))
    ltx_helper.send(msgpack.packb([3, 1, paths[0], "FOO"]))

    log = ltx_helper.unpack_next()
    assert log[0] == 4
    assert log[3] == "foo-bar-baz\n"
    res = ltx_helper.unpack_next()
    assert res[0] == 5
    assert res[3] == 1
    assert res[4] == 0
