"""
Unittests for Dispatcher implementations.
"""
import os
import time
import stat
import shutil
import random
import pytest
from typing import IO
from ltp.sut import SUT, SUTTimeoutError
from ltp.dispatcher import SerialDispatcher
from ltp.events import SyncEventHandler


class MySUT(SUT):
    """
    Internal implementation of SUT.
    """

    def __init__(self, stdout: bytes, iobuffer: IO = None) -> None:
        self._stdout = stdout
        self._iobuffer = iobuffer
        self._running = False

    def stop(self, timeout: float = 30) -> None:
        if timeout < 0:
            raise SUTTimeoutError("Timeout during stop")

    def force_stop(self, timeout: float = 30) -> None:
        if timeout < 0:
            raise SUTTimeoutError("Timeout during stop")

    def is_running(self) -> bool:
        return self._running

    def communicate(self, timeout: float = 3600) -> None:
        if timeout < 0:
            raise SUTTimeoutError("Timeout during communicate")

        self._running = True

    def run_command(self, command: str, timeout: float = 3600) -> dict:
        t_start = time.time()

        if self._iobuffer:
            length = len(self._stdout)
            index = 0

            while index < length:
                size = random.randint(1, 1024)
                data = None

                if index + size > length:
                    data = self._stdout[index:]
                    index = length
                else:
                    data = self._stdout[index: index + size]
                    index += size

                self._iobuffer.write(data)
                self._iobuffer.flush()

        if timeout < 0:
            raise SUTTimeoutError(f"Timeout running '{command}' execution")

        t_end = time.time() - t_start

        ret = {
            "command": command,
            "stdout": self._stdout,
            "returncode": 0,
            "timeout": timeout,
            "exec_time": t_end,
        }

        return ret

    def fetch_file(self, target_path: str, local_path: str, timeout: float = 3600) -> None:
        shutil.copyfile(target_path, local_path)

class _TestDispatcher:
    """
    Test Dispatcher API.
    """

    @pytest.fixture
    def sut(self):
        """
        Mocked SUT to test dispatcher.
        """
        raise NotImplementedError()

    @pytest.fixture
    def dispatcher(self, sut):
        """
        Dispatcher object to communicate with.
        """
        raise NotImplementedError()

    @pytest.fixture(autouse=True)
    def prepare_tmpdir(self, tmpdir):
        """
        Prepare the temporary directory adding suites and tests.
        """
        # create testcases folder
        testcases = tmpdir.mkdir("testcases").mkdir("bin")

        script_sh = testcases.join("script.sh")
        script_sh.write(
            '#!/bin/bash\n'
            'echo ""\n'
            'echo ""\n'
            'echo "Summary:"\n'
            'echo "passed   $1"\n'
            'echo "failed   $2"\n'
            'echo "broken   $3"\n'
            'echo "skipped  $4"\n'
            'echo "warnings $5"\n'
        )

        st = os.stat(str(script_sh))
        os.chmod(str(script_sh), st.st_mode | stat.S_IEXEC)

        # create runtest folder
        root = tmpdir.mkdir("runtest")

        suitefile = root.join("dirsuite0")
        suitefile.write("dir01 script.sh 1 0 0 0 0")

        suitefile = root.join("dirsuite1")
        suitefile.write("dir02 script.sh 0 1 0 0 0")

        suitefile = root.join("dirsuite2")
        suitefile.write("dir03 script.sh 0 0 0 1 0")

        suitefile = root.join("dirsuite3")
        suitefile.write("dir04 script.sh 0 0 1 0 0")

        suitefile = root.join("dirsuite4")
        suitefile.write("dir05 script.sh 0 0 0 0 1")

        # create scenario_groups folder
        scenario_dir = tmpdir.mkdir("scenario_groups")

        scenario_def = scenario_dir.join("default")
        scenario_def.write("dirsuite0\ndirsuite1")

        scenario_def = scenario_dir.join("network")
        scenario_def.write("dirsuite2\ndirsuite3\ndirsuite4\ndirsuite5")
                                                                   
    def test_exec_suites(self, dispatcher):
        """
        Test exec_suites method.
        """
        results = dispatcher.exec_suites([
            "dirsuite0",
            "dirsuite1",
            "dirsuite2",
        ])

class TestSerialDispatcher(_TestDispatcher):
    """
    Test SerialDispatcher implementation.
    """

    @pytest.fixture
    def sut(self):
        """
        Mocked SUT to test dispatcher.
        """
        return MySUT("", None)

    @pytest.fixture
    def dispatcher(self, sut, tmpdir):
        """
        Dispatcher object to communicate with.
        """
        events = SyncEventHandler()
        return SerialDispatcher(
            ltpdir=str(tmpdir),
            tmpdir=str(tmpdir),
            sut=sut,
            events=events)
