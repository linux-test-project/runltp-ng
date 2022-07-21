"""
Tests for LTX python library.
"""
import time
import signal
import threading
import pytest
from ltx import LTX
from ltx import LTXError


@pytest.fixture
def ltx(executor):
    """
    LTX object to test.
    """
    stdin = executor.stdin.fileno()
    stdout = executor.stdout.fileno()

    yield LTX(stdin, stdout)


def test_version(ltx):
    """
    Test version method.
    """
    version = ltx.version()
    assert version


@pytest.mark.parametrize("count", [1, LTX.TABLE_ID_MAXSIZE + 100])
def test_ping(ltx, count):
    """
    Test ping method.
    """
    for _ in range(0, count):
        time_ns = ltx.ping()
        assert time_ns > 0


def test_ping_timeout(ltx):
    """
    Test ping method on timeout.
    """
    with pytest.raises(LTXError):
        ltx.ping(timeout=0)


def test_reserve(ltx):
    """
    Test table_id reservation.
    """
    for i in range(0, LTX.TABLE_ID_MAXSIZE):
        table_id = ltx.reserve()
        assert i == table_id

    with pytest.raises(LTXError):
        ltx.reserve()
        ltx.reserve()
        ltx.reserve()


@pytest.mark.parametrize("count", [1, LTX.TABLE_ID_MAXSIZE + 100])
def test_execute(ltx, count, whereis):
    """
    Test execute method.
    """
    for _ in range(0, count):
        table_id = ltx.reserve()

        stdout, time_ns, si_code, si_status = ltx.execute(
            table_id,
            whereis("uname")[0],
            timeout=0.5)
        assert stdout == "Linux\n"
        assert time_ns > 0
        assert si_code == 1
        assert si_status == 0


def test_execute_timeout(ltx, whereis):
    """
    Test execute method on timeout.
    """
    table_id = ltx.reserve()
    with pytest.raises(LTXError):
        paths = whereis("sleep")
        ltx.execute(table_id, f"{paths[0]} 10", timeout=0)


@pytest.mark.parametrize("count", [1, LTX.TABLE_ID_MAXSIZE + 100])
def test_kill(ltx, count, whereis):
    """
    Test kill method.
    """
    class SleepThread(threading.Thread):
        """
        Thread for testing purpose running sleep command using LTX.
        """
        stdout = ""
        time_ns = 0
        si_code = 0
        si_status = 0

        def run(self) -> None:
            paths = whereis("sleep")
            self.stdout, \
                self.time_ns, \
                self.si_code, \
                self.si_status = ltx.execute(
                    table_id,
                    f"{paths[0]} 4",
                    timeout=6)

    for _ in range(0, count):
        table_id = ltx.reserve()

        thread = SleepThread(daemon=True)
        thread.start()

        time.sleep(0.1)
        ltx.kill(table_id)

        thread.join()

        assert thread.stdout == ""
        assert thread.time_ns > 0
        assert thread.si_code == 2
        assert thread.si_status == signal.SIGKILL


@pytest.mark.parametrize("count", [1, LTX.TABLE_ID_MAXSIZE + 100])
def test_env_no_table_id(ltx, count, whereis):
    """
    Test env method without table_id.
    """
    paths = whereis("printenv")

    for _ in range(0, count):
        ltx.env(None, "HELLO", "world")

        table_id = ltx.reserve()
        stdout, time_ns, si_code, si_status = ltx.execute(
            table_id,
            f"{paths[0]} HELLO",
            timeout=1)

        assert "world" in stdout
        assert time_ns > 0
        assert si_code == 1
        assert si_status == 0


@pytest.mark.parametrize("count", [1, LTX.TABLE_ID_MAXSIZE + 100])
def test_env_with_table_id(ltx, count, whereis):
    """
    Test env method using table_id.
    """
    paths = whereis("printenv")

    for _ in range(0, count):
        table_id = ltx.reserve()

        ltx.env(table_id, "HELLO", "world")
        stdout, time_ns, si_code, si_status = ltx.execute(
            table_id,
            f"{paths[0]} HELLO",
            timeout=1)

        assert "world" in stdout
        assert time_ns > 0
        assert si_code == 1
        assert si_status == 0


def test_env_timeout(ltx):
    """
    Test env method on timeout.
    """
    with pytest.raises(LTXError):
        ltx.env(None, "HELLO", "world", timeout=0)


def test_get_file(tmp_path, ltx):
    """
    Test get_file method.
    """
    pattern = b'AaXa\x00\x01\x02Zz' * 2048

    myfile = tmp_path / "file.txt"
    myfile.write_bytes(pattern)

    data = ltx.get_file(myfile.as_posix())

    assert data == pattern


def test_get_file_timeout(tmp_path, ltx):
    """
    Test get_file method on timeout.
    """
    pattern = b'AaXa\x00\x01\x02Zz' * 2048

    myfile = tmp_path / "file.txt"
    myfile.write_bytes(pattern)

    with pytest.raises(LTXError):
        ltx.get_file(myfile.as_posix(), timeout=0)


def test_set_file(tmp_path, ltx):
    """
    Test set_file method.
    """
    pattern = b'AaXa\x00\x01\x02Zz' * 2048

    myfile = tmp_path / "file.txt"

    ltx.set_file(myfile.as_posix(), pattern)

    content = myfile.read_bytes()
    assert content == pattern


def test_set_file_timeout(tmp_path, ltx):
    """
    Test set_file method on timeout.
    """
    pattern = b'AaXa\x00\x01\x02Zz' * 2048

    myfile = tmp_path / "file.txt"

    with pytest.raises(LTXError):
        ltx.set_file(myfile.as_posix(), pattern, timeout=0)
