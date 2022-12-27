"""
Test SUT implementations.
"""
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import pytest
from ltp.sut import IOBuffer
from ltp.sut import SUTTimeoutError
from ltp.host import HostSUT
from ltp.tests.sut import _TestSUT
from ltp.tests.sut import Printer


@pytest.fixture
def sut():
    sut = HostSUT()
    sut.setup()

    yield sut

    if sut.is_running:
        sut.force_stop()


class TestHostSUT(_TestSUT):
    """
    Test HostSUT implementation.
    """

    @pytest.fixture
    def sut_stop_sleep(self, request):
        """
        Host SUT test doesn't require time sleep in `test_stop_communicate`.
        """
        return request.param * 0

    def test_cwd(self, tmpdir):
        """
        Test CWD constructor argument.
        """
        myfile = tmpdir / "myfile"
        myfile.write("runltp-ng tests")

        sut = HostSUT()
        sut.setup(cwd=str(tmpdir))
        sut.communicate(iobuffer=Printer())

        ret = sut.run_command("cat myfile", timeout=2, iobuffer=Printer())
        assert ret["returncode"] == 0
        assert ret["stdout"] == "runltp-ng tests"

    def test_env(self, tmpdir):
        """
        Test ENV constructor argument.
        """
        myfile = tmpdir / "myfile"
        myfile.write("runltp-ng tests")

        sut = HostSUT()
        sut.setup(cwd=str(tmpdir), env=dict(FILE=str(myfile)))
        sut.communicate(iobuffer=Printer())

        ret = sut.run_command("cat $FILE", timeout=2, iobuffer=Printer())
        assert ret["returncode"] == 0
        assert ret["stdout"] == "runltp-ng tests"

    def test_multiple_commands(self, sut):
        """
        Execute run_command multiple times.
        """
        sut.communicate()

        def _runner(index):
            return sut.run_command(f"echo -n {index}", timeout=15)

        results = []

        with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
            for result in executor.map(_runner, range(100)):
                results.append(result)

        for i in range(100):
            data = results[i]

            assert data["command"] == f"echo -n {i}"
            assert data["timeout"] == 15
            assert data["returncode"] == 0
            assert data["stdout"] == f"{i}"
            assert 0 < data["exec_time"] < time.time()

    def test_multiple_commands_timeout(self, sut):
        """
        Execute run_command multiple times with low timeout.
        """
        sut.communicate()

        def _runner(_):
            with pytest.raises(SUTTimeoutError):
                sut.run_command("sleep 1", timeout=0.1)

        with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
            executor.map(_runner, range(100))

    def test_multiple_commands_stop(self, sut):
        """
        Execute run_command multiple time, then call stop().
        """
        class MyBuffer(IOBuffer):
            """
            For each echo command, we store 1 inside `executed` list.
            At the end of all commands executions we know how many
            commands are sleeping by checking `executed` list.
            """
            executed = []

            def write(self, _: str) -> None:
                self.executed.append(1)

            def flush(self) -> None:
                pass

        buffer = MyBuffer()
        results = []
        cpu_count = os.cpu_count()
        exec_count = cpu_count - 1
        sut.communicate()

        def _threaded():
            def _runner(index):
                return sut.run_command(
                    f"echo -n {index}; sleep 3",
                    timeout=5,
                    iobuffer=buffer)

            with ThreadPoolExecutor(max_workers=cpu_count) as executor:
                for result in executor.map(_runner, range(exec_count)):
                    results.append(result)

        thread = threading.Thread(target=_threaded, daemon=True)
        thread.start()

        while len(buffer.executed) < exec_count:
            time.sleep(0.001)
            continue

        sut.force_stop()

        while len(results) < exec_count:
            time.sleep(0.001)
            continue

        for i in range(exec_count):
            data = results[i]

            assert data["command"] == f"echo -n {i}; sleep 3"
            assert data["timeout"] == 5
            assert data["returncode"] != 0
            assert data["stdout"] == f"{i}"
            assert 0 < data["exec_time"] < time.time()
