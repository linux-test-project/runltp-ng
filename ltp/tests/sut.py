"""
Test SUT implementations.
"""
import os
import time
import pytest
import logging
import threading
from ltp.sut import SUTError
from ltp.sut import SUTTimeoutError


class Printer:
    """
    stdout printer.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger("test.host")
        self._line = ""

    def write(self, data):
        data_str = data.decode(encoding="utf-8", errors="replace")

        if len(data_str) == 1:
            self._line += data_str
            if data_str == "\n":
                self._logger.info(self._line[:-1])
                self._line = ""
        else:
            lines = data_str.split('\n')
            for line in lines[:-1]:
                self._line += line
                self._logger.info(self._line)
                self._line = ""

            self._line = lines[-1]

            if data_str.endswith('\n') and self._line:
                self._logger.info(self._line)
                self._line = ""

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

    def test_communicate(self, sut):
        """
        Test communicate method.
        """
        sut.communicate(iobuffer=Printer())
        with pytest.raises(SUTError):
            sut.communicate(iobuffer=Printer())
        sut.stop()

    @pytest.mark.parametrize("force", [True, False])
    @pytest.mark.parametrize("sleep_t", [1, 13])
    def test_stop_communicate(self, sut, force, sleep_t):
        """
        Test stop method when running communicate.
        """
        def _threaded():
            time.sleep(sleep_t)

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
        try:
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
        finally:
            sut.stop(iobuffer=Printer())

    @pytest.mark.parametrize("force", [True, False])
    def test_stop_run_command(self, sut, force):
        """
        Test stop when command is running.
        """
        sut.communicate(iobuffer=Printer())

        def _threaded():
            time.sleep(1)

            if force:
                sut.force_stop(timeout=4, iobuffer=Printer())
            else:
                sut.stop(timeout=4, iobuffer=Printer())

        thread = threading.Thread(target=_threaded, daemon=True)
        thread.start()

        sut.run_command("sleep 20", timeout=25)
        t_start = time.time()
        while sut.is_running:
            assert time.time() - t_start < 30

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

    def test_fetch_file(self, sut):
        """
        Test fetch_file method.
        """
        sut.communicate(iobuffer=Printer())

        try:
            for i in range(0, 5):
                myfile = f"/tmp/myfile{i}"
                sut.run_command(
                    f"echo -n 'runltp-ng tests' > {myfile}",
                    timeout=1)
                data = sut.fetch_file(myfile, timeout=1)

                assert data == b"runltp-ng tests"
        finally:
            sut.stop(iobuffer=Printer())

    def test_stop_fetch_file(self, tmpdir, sut):
        """
        Test stop method when running fetch_file.
        """
        target_path = tmpdir / "target_file"
        target = str(target_path)

        # create a big file to have enough IO traffic and slow
        # down fetch_file() method
        with open(target, 'wb') as ftarget:
            ftarget.seek(1*1024*1024*1024-1)
            ftarget.write(b'\0')

        sentinel = str(tmpdir / "fire")

        def _threaded():
            sut.communicate(iobuffer=Printer())
            with open(sentinel, 'w') as f:
                f.write("data")
            sut.fetch_file(target, timeout=10)

        thread = threading.Thread(target=_threaded)
        thread.start()

        start_t = time.time()
        while not sut.is_running:
            time.sleep(0.05)
            assert time.time() - start_t < 10

        # wait for local file creation before stop
        start_t = time.time()
        while not os.path.isfile(sentinel):
            time.sleep(0.05)
            assert time.time() - start_t < 60

        sut.stop(iobuffer=Printer())
        thread.join()

    def test_fetch_file_timeout(self, tmpdir, sut):
        """
        Test stop method when running fetch_file.
        """
        target_path = tmpdir / "target_file"
        target = str(target_path)

        # create a big file to have enough IO traffic and slow
        # down fetch_file() method
        with open(target, 'wb') as ftarget:
            ftarget.seek(1*1024*1024*1024-1)
            ftarget.write(b'\0')

        sut.communicate(iobuffer=Printer())

        try:
            with pytest.raises(SUTTimeoutError):
                sut.fetch_file(target, timeout=0)
        finally:
            sut.stop(iobuffer=Printer())
