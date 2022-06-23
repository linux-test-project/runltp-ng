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
        sut.communicate()
        with pytest.raises(SUTError):
            sut.communicate()
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
                sut.force_stop(timeout=4)
            else:
                sut.stop(timeout=4)

        thread = threading.Thread(target=_threaded, daemon=True)
        thread.start()

        sut.communicate()

        thread.join()

    def test_run_command(self, sut):
        """
        Test command run.
        """
        try:
            sut.communicate()

            for _ in range(0, 100):
                data = sut.run_command(
                    "cat /etc/os-release",
                    timeout=1)
                assert data["command"] == "cat /etc/os-release"
                assert data["timeout"] == 1
                assert data["returncode"] == 0
                assert "ID=" in data["stdout"]
                assert 0 < data["exec_time"] < time.time()
        finally:
            sut.stop()

    @pytest.mark.parametrize("force", [True, False])
    def test_stop_run_command(self, sut, force):
        """
        Test stop when command is running.
        """
        sut.communicate()

        def _threaded():
            time.sleep(1)

            if force:
                sut.force_stop(timeout=4)
            else:
                sut.stop(timeout=4)

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
        sut.communicate()

        with pytest.raises(SUTTimeoutError):
            sut.run_command("sleep 2", timeout=0.5)

    def test_fetch_file_bad_args(self, tmpdir, sut):
        """
        Test fetch_file method with bad arguments.
        """
        with pytest.raises(ValueError):
            sut.fetch_file(None, "local_file")

        target_path = tmpdir / "target_file"
        target_path.write("runltp-ng tests")
        with pytest.raises(ValueError):
            sut.fetch_file(str(target_path), None)

        with pytest.raises(ValueError):
            sut.fetch_file("this_file_doesnt_exist", None)

    def test_fetch_file(self, tmpdir, sut):
        """
        Test fetch_file method.
        """
        sut.communicate()

        try:
            for i in range(0, 5):
                local_path = tmpdir / f"local_file{i}"
                target_path = tmpdir / f"target_file{i}"
                target_path.write("runltp-ng tests")

                target = str(target_path)
                local = str(local_path)

                sut.fetch_file(target, local)

                assert os.path.isfile(local)
                assert open(target, 'r').read() == "runltp-ng tests"
        finally:
            sut.stop()

    def test_stop_fetch_file(self, tmpdir, sut):
        """
        Test stop method when running fetch_file.
        """
        local_path = tmpdir / "local_file"
        target_path = tmpdir / "target_file"

        target = str(target_path)
        local = str(local_path)

        # create a big file to have enough IO traffic and slow
        # down fetch_file() method
        with open(target, 'wb') as ftarget:
            ftarget.seek(1*1024*1024*1024-1)
            ftarget.write(b'\0')

        def _threaded():
            sut.communicate()
            sut.fetch_file(target, local)

        thread = threading.Thread(target=_threaded)
        thread.start()

        start_t = time.time()
        while not sut.is_running:
            time.sleep(0.05)
            assert time.time() - start_t < 10

        # wait for local file creation before stop
        start_t = time.time()
        while not os.path.isfile(local_path):
            time.sleep(0.05)
            assert time.time() - start_t < 60

        sut.stop()
        thread.join()

        target_size = os.stat(target).st_size
        local_size = os.stat(local).st_size

        assert target_size != local_size

    def test_fetch_file_timeout(self, tmpdir, sut):
        """
        Test stop method when running fetch_file.
        """
        local_path = tmpdir / "local_file"
        target_path = tmpdir / "target_file"

        target = str(target_path)
        local = str(local_path)

        # create a big file to have enough IO traffic and slow
        # down fetch_file() method
        with open(target, 'wb') as ftarget:
            ftarget.seek(1*1024*1024*1024-1)
            ftarget.write(b'\0')

        sut.communicate()

        try:
            with pytest.raises(SUTTimeoutError):
                sut.fetch_file(target, local, timeout=0)
        finally:
            sut.stop()
