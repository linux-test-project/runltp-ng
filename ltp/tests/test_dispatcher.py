"""
Unittests for Dispatcher implementations.
"""
import os
import math
import stat
import queue
from unittest.mock import MagicMock
import pytest
import ltp
import ltp.sut
from ltp.sut import SUTError
from ltp.host import HostSUT
from ltp.dispatcher import SerialDispatcher
from ltp.dispatcher import SuiteTimeoutError
from ltp.tempfile import TempDir


class TestSerialDispatcher:
    """
    Test SerialDispatcher implementation.
    """

    @pytest.fixture(autouse=True, scope="function")
    def setup(self):
        """
        Setup events before test.
        """
        ltp.events.start_event_loop()

        yield

        ltp.events.stop_event_loop()
        ltp.events.reset()

    @pytest.fixture
    def sut(self, tmpdir):
        """
        Initialized SUT instance
        """
        testcases = str(tmpdir / "ltp" / "testcases" / "bin")

        env = {}
        env["PATH"] = "/sbin:/usr/sbin:/usr/local/sbin:" + \
            f"/root/bin:/usr/local/bin:/usr/bin:/bin:{testcases}"

        sut = HostSUT()
        sut.setup(cwd=testcases, env=env)
        # hack: force the SUT to be recognized as a different host
        # so we can reboot it
        sut.NAME = "testing_host"
        sut.communicate()

        return sut

    @pytest.fixture
    def prepare_tmpdir(self, tmpdir):
        """
        Prepare the temporary directory adding suites and tests.
        """
        # create testcases folder
        ltpdir = tmpdir.mkdir("ltp")
        testcases = ltpdir.mkdir("testcases").mkdir("bin")

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
        runtest = ltpdir.mkdir("runtest")

        suitefile = runtest.join("dirsuite0")
        suitefile.write("dir01 script.sh 1 0 0 0 0")

        suitefile = runtest.join("dirsuite1")
        suitefile.write("dir02 script.sh 0 1 0 0 0")

        suitefile = runtest.join("dirsuite2")
        suitefile.write("dir03 script.sh 0 0 0 1 0")

        suitefile = runtest.join("dirsuite3")
        suitefile.write("dir04 script.sh 0 0 1 0 0")

        suitefile = runtest.join("dirsuite4")
        suitefile.write("dir05 script.sh 0 0 0 0 1")

        # create scenario_groups folder
        scenario_dir = ltpdir.mkdir("scenario_groups")

        scenario_def = scenario_dir.join("default")
        scenario_def.write("dirsuite0\ndirsuite1")

        scenario_def = scenario_dir.join("network")
        scenario_def.write("dirsuite2\ndirsuite3\ndirsuite4\ndirsuite5")

    def test_bad_constructor(self, tmpdir, sut):
        """
        Test constructor with bad arguments.
        """
        with pytest.raises(ValueError):
            SerialDispatcher(
                tmpdir=TempDir(root=tmpdir),
                ltpdir=None,
                sut=sut)

        with pytest.raises(ValueError):
            SerialDispatcher(
                tmpdir=TempDir(root=tmpdir),
                ltpdir=str(tmpdir),
                sut=None)

    @pytest.mark.usefixtures("prepare_tmpdir")
    def test_exec_suites_bad_args(self, tmpdir, sut):
        """
        Test exec_suites() method with bad arguments.
        """
        dispatcher = SerialDispatcher(
            tmpdir=TempDir(root=tmpdir),
            ltpdir=str(tmpdir / "ltp"),
            sut=sut)

        sut.get_tainted_info = MagicMock(return_value=(0, ""))

        try:
            with pytest.raises(ValueError):
                dispatcher.exec_suites(None)

            with pytest.raises(SUTError):
                dispatcher.exec_suites(["this_suite_doesnt_exist"])
        finally:
            sut.stop()

    @pytest.mark.usefixtures("prepare_tmpdir")
    def test_exec_suites(self, tmpdir, sut):
        """
        Test exec_suites() method.
        """
        dispatcher = SerialDispatcher(
            tmpdir=TempDir(root=tmpdir),
            ltpdir=str(tmpdir / "ltp"),
            sut=sut)

        sut.get_tainted_info = MagicMock(return_value=(0, ""))

        try:
            results = dispatcher.exec_suites(suites=["dirsuite0", "dirsuite2"])

            assert len(results) == 2

            assert results[0].suite.name == "dirsuite0"
            assert results[0].tests_results[0].passed == 1
            assert results[0].tests_results[0].failed == 0
            assert results[0].tests_results[0].skipped == 0
            assert results[0].tests_results[0].warnings == 0
            assert results[0].tests_results[0].broken == 0
            assert results[0].tests_results[0].return_code == 0
            assert results[0].tests_results[0].exec_time > 0

            assert results[1].suite.name == "dirsuite2"
            assert results[1].tests_results[0].passed == 0
            assert results[1].tests_results[0].failed == 0
            assert results[1].tests_results[0].skipped == 1
            assert results[1].tests_results[0].warnings == 0
            assert results[1].tests_results[0].broken == 0
            assert results[1].tests_results[0].return_code == 0
            assert results[1].tests_results[0].exec_time > 0
        finally:
            sut.stop()

    @pytest.mark.usefixtures("prepare_tmpdir")
    def test_stop(self, tmpdir, sut):
        """
        Test stop method during exec_suites.
        """
        dispatcher = SerialDispatcher(
            tmpdir=TempDir(root=tmpdir),
            ltpdir=str(tmpdir / "ltp"),
            sut=sut)

        def stop_exec_suites(_):
            dispatcher.stop(timeout=3)

        ltp.events.register("test_started", stop_exec_suites)

        sut.get_tainted_info = MagicMock(return_value=(0, ""))

        results = dispatcher.exec_suites(suites=["dirsuite0", "dirsuite2"])

        assert len(results) == 1
        assert results[0].passed == 1
        assert len(results[0].tests_results) == 1

    @pytest.mark.usefixtures("prepare_tmpdir")
    def test_exec_suites_all(self, tmpdir, sut):
        """
        Test exec_suites() method executing all different kind of tests.
        """
        dispatcher = SerialDispatcher(
            tmpdir=TempDir(root=tmpdir),
            ltpdir=str(tmpdir / "ltp"),
            sut=sut)

        sut.get_tainted_info = MagicMock(return_value=(0, ""))

        try:
            results = dispatcher.exec_suites(suites=[
                "dirsuite0",
                "dirsuite1",
                "dirsuite2",
                "dirsuite3",
                "dirsuite4"])

            assert len(results) == 5

            assert results[0].suite.name == "dirsuite0"
            assert results[0].tests_results[0].passed == 1
            assert results[0].tests_results[0].failed == 0
            assert results[0].tests_results[0].skipped == 0
            assert results[0].tests_results[0].warnings == 0
            assert results[0].tests_results[0].broken == 0
            assert results[0].tests_results[0].return_code == 0
            assert results[0].tests_results[0].exec_time > 0

            assert results[1].suite.name == "dirsuite1"
            assert results[1].tests_results[0].passed == 0
            assert results[1].tests_results[0].failed == 1
            assert results[1].tests_results[0].skipped == 0
            assert results[1].tests_results[0].warnings == 0
            assert results[1].tests_results[0].broken == 0
            assert results[1].tests_results[0].return_code == 0
            assert results[1].tests_results[0].exec_time > 0

            assert results[2].suite.name == "dirsuite2"
            assert results[2].tests_results[0].passed == 0
            assert results[2].tests_results[0].failed == 0
            assert results[2].tests_results[0].skipped == 1
            assert results[2].tests_results[0].warnings == 0
            assert results[2].tests_results[0].broken == 0
            assert results[2].tests_results[0].return_code == 0
            assert results[2].tests_results[0].exec_time > 0

            assert results[3].suite.name == "dirsuite3"
            assert results[3].tests_results[0].passed == 0
            assert results[3].tests_results[0].failed == 0
            assert results[3].tests_results[0].skipped == 0
            assert results[3].tests_results[0].warnings == 0
            assert results[3].tests_results[0].broken == 1
            assert results[3].tests_results[0].return_code == 0
            assert results[3].tests_results[0].exec_time > 0

            assert results[4].suite.name == "dirsuite4"
            assert results[4].tests_results[0].passed == 0
            assert results[4].tests_results[0].failed == 0
            assert results[4].tests_results[0].skipped == 0
            assert results[4].tests_results[0].warnings == 1
            assert results[4].tests_results[0].broken == 0
            assert results[4].tests_results[0].return_code == 0
            assert results[4].tests_results[0].exec_time > 0
        finally:
            sut.stop()

    @pytest.mark.usefixtures("prepare_tmpdir")
    def test_exec_suites_suite_timeout(self, tmpdir, sut):
        """
        Test exec_suites() method when suite timeout occurs.
        """
        ltpdir = tmpdir / "ltp"
        runtest = ltpdir / "runtest"

        sleepsuite = runtest.join("sleepsuite")
        sleepsuite.write("sleep sleep 2")

        dispatcher = SerialDispatcher(
            tmpdir=TempDir(root=tmpdir),
            ltpdir=str(ltpdir),
            sut=sut,
            suite_timeout=0.5,
            test_timeout=15)

        sut.get_tainted_info = MagicMock(return_value=(0, ""))

        try:
            with pytest.raises(SuiteTimeoutError):
                dispatcher.exec_suites(suites=["sleepsuite"])
        finally:
            sut.stop()

    @pytest.mark.usefixtures("prepare_tmpdir")
    def test_exec_suites_test_timeout(self, tmpdir, sut):
        """
        Test exec_suites() method when test timeout occurs.
        """
        ltpdir = tmpdir / "ltp"
        runtest = ltpdir / "runtest"

        sleepsuite = runtest.join("sleepsuite")
        sleepsuite.write("sleep sleep 2")

        dispatcher = SerialDispatcher(
            tmpdir=TempDir(root=tmpdir),
            ltpdir=str(ltpdir),
            sut=sut,
            suite_timeout=15,
            test_timeout=0.5)

        sut.get_tainted_info = MagicMock(return_value=(0, ""))

        try:
            ret = dispatcher.exec_suites(suites=["sleepsuite"])
        finally:
            sut.stop()

        assert ret[0].tests_results[0].return_code == -1

    @pytest.mark.usefixtures("prepare_tmpdir")
    def test_kernel_tainted(self, tmpdir, sut):
        """
        Test tainted kernel recognition.
        """
        ltpdir = tmpdir / "ltp"

        dispatcher = SerialDispatcher(
            tmpdir=TempDir(root=tmpdir),
            ltpdir=str(ltpdir),
            sut=sut,
            suite_timeout=0.5,
            test_timeout=15)

        class TaintChecker:
            def __init__(self, dispatcher, bit, msg) -> None:
                self._dispatcher = dispatcher
                self._bit = bit
                self._msg = msg
                self._first = True
                self.tainted_msg = queue.Queue()
                self.rebooted = queue.Queue()

            def kernel_tainted(self, msg: str):
                if self._first:
                    self._first = False

                    # now we change tainted information to trigger
                    # sut_restart event
                    sut.get_tainted_info = MagicMock(
                        return_value=(self._bit, [self._msg]))
                else:
                    self.tainted_msg.put(msg)

            def sut_restart(self, name: str):
                self.rebooted.put(True)

        try:
            for i in range(0, 18):
                bit = math.pow(2, i)
                msg = ltp.sut.TAINTED_MSG[i]

                sut.get_tainted_info = MagicMock(return_value=(0, [""]))

                checker = TaintChecker(dispatcher, bit, msg)
                ltp.events.register("kernel_tainted", checker.kernel_tainted)
                ltp.events.register("sut_restart", checker.sut_restart)

                dispatcher.exec_suites(suites=["dirsuite0"])

                assert checker.tainted_msg.get() == msg
                assert checker.rebooted.get()

                ltp.events.unregister("kernel_tainted")
                ltp.events.unregister("sut_restart")
        finally:
            sut.stop()

    @pytest.mark.usefixtures("prepare_tmpdir")
    def test_kernel_panic(self, tmpdir, sut):
        """
        Test kernel panic recognition.
        """
        if sut.name == "testing_host":
            pytest.skip("Not supported on Host")

        ltpdir = tmpdir / "ltp"
        runtest = ltpdir / "runtest"

        # just write "Kernel panic" on stdout and trigger the dispatcher
        crashsuite = runtest.join("crashme")
        crashsuite.write(f"kernel_panic echo Kernel panic")

        dispatcher = SerialDispatcher(
            tmpdir=TempDir(root=tmpdir),
            ltpdir=str(ltpdir),
            sut=sut,
            suite_timeout=10,
            test_timeout=10)

        sut.get_tainted_info = MagicMock(return_value=(0, ""))

        class PanicChecker:
            def __init__(self) -> None:
                self.panic = False
                self.rebooted = False

            def kernel_panic(self):
                self.panic = True

            def sut_restart(self, name: str):
                self.rebooted = True

        checker = PanicChecker()
        ltp.events.register("kernel_panic", checker.kernel_panic)
        ltp.events.register("sut_restart", checker.sut_restart)

        try:
            ret = dispatcher.exec_suites(suites=["crashme"])

            assert ret[0].tests_results[0].return_code == -1
            assert checker.panic
            assert checker.rebooted
        finally:
            sut.stop()
