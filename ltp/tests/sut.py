"""
Test SUT implementations.
"""
import time
import queue
import pytest
import logging
import threading
from ltp.sut import IOBuffer
from ltp.sut import SUTError
from ltp.sut import SUTTimeoutError
from ltp.utils import Timeout


class Printer(IOBuffer):
    """
    stdout printer.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger("test.host")
        self._line = ""

    def write(self, data: str) -> None:
        print(data, end="")

    def flush(self):
        pass


@pytest.fixture
def sut():
    """
    Expose the SUT implementation via this fixture in order to test it.
    """
    raise NotImplementedError()


class _TestSUT:
    """
    Generic tests for SUT implementation.
    """

    _logger = logging.getLogger("test.sut")

    def test_ping_no_running(self, sut):
        """
        Test ping method with no running sut.
        """
        with pytest.raises(SUTError):
            sut.ping()

    def test_ping(self, sut):
        """
        Test ping method.
        """
        sut.communicate(iobuffer=Printer())
        ping_t = sut.ping()

        assert ping_t > 0

    def test_get_info(self, sut):
        """
        Test get_info method.
        """
        sut.communicate(iobuffer=Printer())
        info = sut.get_info()

        assert info["distro"]
        assert info["distro_ver"]
        assert info["kernel"]
        assert info["arch"]

    def test_get_tainted_info(self, sut):
        """
        Test get_tainted_info.
        """
        sut.communicate(iobuffer=Printer())
        code, messages = sut.get_tainted_info()

        assert code >= 0
        assert isinstance(messages, list)

    def test_communicate(self, sut):
        """
        Test communicate method.
        """
        sut.communicate(iobuffer=Printer())
        with pytest.raises(SUTError):
            sut.communicate(iobuffer=Printer())
        sut.stop()

    def test_ensure_communicate(self, sut):
        """
        Test ensure_communicate method.
        """
        sut.ensure_communicate(iobuffer=Printer())
        with pytest.raises(SUTError):
            sut.ensure_communicate(iobuffer=Printer(), retries=1)

        sut.ensure_communicate(iobuffer=Printer(), retries=10)
        sut.stop()

    @pytest.fixture
    def sut_stop_sleep(self, request):
        """
        Setup sleep time before calling stop after communicate.
        By changing multiply factor it's possible to tweak stop sleep and
        change the behaviour of `test_stop_communicate`.
        """
        return request.param * 1.0

    @pytest.mark.parametrize("force", [True, False])
    @pytest.mark.parametrize("sut_stop_sleep", [1, 2], indirect=True)
    def test_stop_communicate(self, sut, force, sut_stop_sleep):
        """
        Test stop method when running communicate.
        """
        def _threaded():
            time.sleep(sut_stop_sleep)

            if force:
                sut.force_stop(timeout=4, iobuffer=Printer())
            else:
                sut.stop(timeout=4, iobuffer=Printer())

        thread = threading.Thread(target=_threaded, daemon=True)
        thread.start()

        sut.communicate(iobuffer=Printer())

        thread.join()

    def test_run_command(self, sut):
        """
        Test command run.
        """
        sut.communicate(iobuffer=Printer())

        for _ in range(0, 100):
            data = sut.run_command(
                "cat /etc/os-release",
                timeout=1,
                iobuffer=Printer())
            assert data["command"] == "cat /etc/os-release"
            assert data["timeout"] == 1
            assert data["returncode"] == 0
            assert "ID=" in data["stdout"]
            assert 0 < data["exec_time"] < time.time()

    @pytest.mark.parametrize("force", [True, False])
    def test_stop_run_command(self, sut, force):
        """
        Test stop when command is running.
        """
        sut.communicate(iobuffer=Printer())

        def _threaded():
            time.sleep(3)

            if force:
                sut.force_stop(timeout=4, iobuffer=Printer())
            else:
                sut.stop(timeout=4, iobuffer=Printer())

        thread = threading.Thread(target=_threaded, daemon=True)
        thread.start()

        sut.run_command("sleep 5", timeout=7)

        with Timeout(7) as timer:
            while sut.is_running:
                time.sleep(0.05)
                timer.check()

    def test_timeout_run_command(self, sut):
        """
        Test run_command on timeout.
        """
        sut.communicate(iobuffer=Printer())

        with pytest.raises(SUTTimeoutError):
            sut.run_command("sleep 2", timeout=0.5)

    def test_fetch_file_bad_args(self, sut):
        """
        Test fetch_file method with bad arguments.
        """
        with pytest.raises(ValueError):
            sut.fetch_file(None)

        with pytest.raises(SUTError):
            sut.fetch_file('this_file_doesnt_exist')

    def test_fetch_file(self, sut):
        """
        Test fetch_file method.
        """
        sut.communicate(iobuffer=Printer())

        for i in range(0, 5):
            myfile = f"/tmp/myfile{i}"
            sut.run_command(
                f"echo -n 'runltp-ng tests' > {myfile}",
                timeout=1)
            data = sut.fetch_file(myfile, timeout=1)

            assert data == b"runltp-ng tests"

    @pytest.mark.parametrize("force", [True, False])
    def test_stop_fetch_file(self, sut, force):
        """
        Test stop method when running fetch_file.
        """
        target_path = "/tmp/target_file"

        sut.communicate(iobuffer=Printer())
        sut.run_command(f"truncate -s {1024*1024*1024} {target_path}")

        def _threaded():
            time.sleep(1)

            if force:
                sut.force_stop(iobuffer=Printer(), timeout=10)
            else:
                sut.stop(iobuffer=Printer(), timeout=10)

        thread = threading.Thread(target=_threaded)
        thread.start()

        sut.fetch_file(target_path, timeout=10)

        thread.join()

    def test_fetch_file_timeout(self, sut):
        """
        Test stop method when running fetch_file.
        """
        target_path = "/tmp/target_file"

        sut.communicate(iobuffer=Printer())
        sut.run_command(f"truncate -s {1024*1024*1024} {target_path}")

        with pytest.raises(SUTTimeoutError):
            sut.fetch_file(target_path, timeout=0)
