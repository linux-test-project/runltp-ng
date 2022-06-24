"""
.. module:: dispatcher
    :platform: Linux
    :synopsis: module containing Dispatcher definition and implementation.

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import re
import time
import logging
import threading
from ltp import LTPException
from ltp.sut import IOBuffer
from ltp.sut import SUTTimeoutError
from ltp.suite import Test
from ltp.suite import Suite
from ltp.results import TestResults
from ltp.results import SuiteResults
from ltp.metadata import Runtest


class DispatcherError(LTPException):
    """
    Raised when a error occurs during dispatcher operations.
    """


class SuiteTimeoutError(LTPException):
    """
    Raised when suite reaches timeout during execution.
    """


class Dispatcher:
    """
    A dispatcher that schedule jobs to run on target.
    """

    @staticmethod
    def _get_test_results(
            test: Test,
            test_data: dict,
            timed_out: bool = False) -> TestResults:
        """
        Return test results accoding with runner output and Test definition.
        :param test: Test definition object
        :type test: Test
        :param test_data: output data from a runner execution
        :type test_data: dict
        :param timed_out: if True, test will be considered broken by default
        :type timed_out: bool
        :returns: TestResults
        """
        stdout = test_data["stdout"]

        match = re.search(
            r"Summary:\n"
            r"passed\s*(?P<passed>\d+)\n"
            r"failed\s*(?P<failed>\d+)\n"
            r"broken\s*(?P<broken>\d+)\n"
            r"skipped\s*(?P<skipped>\d+)\n"
            r"warnings\s*(?P<warnings>\d+)\n",
            stdout
        )

        passed = 0
        failed = 0
        skipped = 0
        broken = 0
        skipped = 0
        warnings = 0
        retcode = test_data["returncode"]
        exec_time = test_data["exec_time"]

        if match:
            passed = int(match.group("passed"))
            failed = int(match.group("failed"))
            skipped = int(match.group("skipped"))
            broken = int(match.group("broken"))
            skipped = int(match.group("skipped"))
            warnings = int(match.group("warnings"))
        else:
            passed = stdout.count("TPASS")
            failed = stdout.count("TFAIL")
            skipped = stdout.count("TSKIP")
            broken = stdout.count("TBROK")
            warnings = stdout.count("TWARN")

            if passed == 0 and \
                    failed == 0 and \
                    skipped == 0 and \
                    broken == 0 and \
                    warnings == 0:
                # if no results are given, this is probably an
                # old test implementation that fails when return
                # code is != 0
                if retcode != 0:
                    failed = 1
                else:
                    passed = 1

        if timed_out:
            broken = 1

        result = TestResults(
            test=test,
            failed=failed,
            passed=passed,
            broken=broken,
            skipped=skipped,
            warnings=warnings,
            exec_time=exec_time,
            retcode=retcode,
            stdout=stdout,
        )

        return result

    @property
    def is_running(self) -> bool:
        """
        Returns True if dispatcher is running tests. False otherwise.
        """
        raise NotImplementedError()

    def stop(self, timeout: float = 30) -> None:
        """
        Stop the current execution.
        :param timeout: timeout before stopping dispatcher
        :type timeout: float
        """
        raise NotImplementedError()

    def exec_suites(self, suites: list) -> list:
        """
        Execute a list of testing suites.
        :param suites: list of Suite objects
        :type suites: list(str)
        :returns: list(SuiteResults)
        """
        raise NotImplementedError()


class KernelPanicError(LTPException):
    """
    Raised during kernel panic.
    """


class KernelPanicChecker(IOBuffer):
    """
    Checks for Kernel panic message and raise an exception.
    """

    def __init__(self) -> None:
        self.stdout = ""

    def write(self, data: bytes) -> None:
        self.stdout += data.decode(encoding="utf-8", errors="replace")
        if "Kernel panic" in self.stdout:
            raise KernelPanicError()

    def flush(self) -> None:
        pass


class SerialDispatcher(Dispatcher):
    """
    Dispatcher implementation that serially runs test suites one after
    the other.
    """

    TAINED_MSG = [
        "proprietary module was loaded",
        "module was force loaded",
        "kernel running on an out of specification system",
        "module was force unloaded",
        "processor reported a Machine Check Exception (MCE)",
        "bad page referenced or some unexpected page flags",
        "taint requested by userspace application",
        "kernel died recently, i.e. there was an OOPS or BUG",
        "ACPI table overridden by user",
        "kernel issued warning",
        "staging driver was loaded",
        "workaround for bug in platform firmware applied",
        "externally-built (“out-of-tree”) module was loaded",
        "unsigned module was loaded",
        "soft lockup occurred",
        "kernel has been live patched",
        "auxiliary taint, defined for and used by distros",
        "kernel was built with the struct randomization plugin"
    ]

    def __init__(self, **kwargs: dict) -> None:
        self._logger = logging.getLogger("ltp.dispatcher")
        self._ltpdir = kwargs.get("ltpdir", None)
        self._tmpdir = kwargs.get("tmpdir", None)
        self._sut = kwargs.get("sut", None)
        self._events = kwargs.get("events", None)
        self._suite_timeout = max(kwargs.get("suite_timeout", 3600.0), 0.0)
        self._test_timeout = max(kwargs.get("test_timeout", 3600.0), 0.0)
        self._exec_lock = threading.Lock()
        self._stop = False

        if not self._ltpdir:
            raise ValueError("LTP directory doesn't exist")

        if not self._tmpdir or not os.path.isdir(self._tmpdir):
            raise ValueError("Temporary directory doesn't exist")

        if not self._sut:
            raise ValueError("SUT object is empty")

        if not self._events:
            raise ValueError("No events are given")

        # create temporary directory where saving suites files
        tmp_suites = os.path.join(self._tmpdir, "runtest")
        if not os.path.isdir(tmp_suites):
            os.mkdir(tmp_suites)

        self._runtest = Runtest(tmp_suites)

    @property
    def is_running(self) -> bool:
        # some pylint versions don't recognize threading.Lock::locked
        # pylint: disable=no-member
        return self._exec_lock.locked()

    def stop(self, timeout: float = 30) -> None:
        if not self.is_running:
            return

        self._logger.info("Stopping dispatcher")

        self._stop = True

        try:
            t_start = time.time()
            t_secs = max(timeout, 0)

            while self.is_running:
                time.sleep(0.1)
                if time.time() - t_start >= t_secs:
                    raise DispatcherError("Timeout when stopping dispatcher")
        finally:
            self._stop = False

        self._logger.info("Dispatcher stopped")

    def _read_available_suites(self) -> list:
        """
        Read the available testing suites by looking at runtest folder using
        ls command.
        """
        runtest_dir = os.path.join(self._ltpdir, "runtest")

        ret = self._sut.run_command(f"ls -1 {runtest_dir}", timeout=10)

        retcode = ret["returncode"]
        if retcode != 0:
            raise DispatcherError("Can't read runtest folder")

        stdout = ret["stdout"]
        suites = [name.rstrip() for name in stdout.split("\n")]

        return suites

    def _download_suites(self, suites: list) -> list:
        """
        Download all testing suites and return suites objects.
        """
        # download all runtest files
        for suite_name in suites:
            target = os.path.join(self._ltpdir, "runtest", suite_name)
            local = os.path.join(self._tmpdir, "runtest", suite_name)

            self._events.fire(
                "suite_download_started",
                suite_name,
                target,
                local)

            self._sut.fetch_file(target, local)

            self._events.fire(
                "suite_download_completed",
                suite_name,
                target,
                local)

        # load all suites objects
        suites_obj = []
        for suite_name in suites:
            suite = self._runtest.read_suite(suite_name)
            suites_obj.append(suite)

        return suites_obj

    def _check_tained(self) -> set:
        """
        Return tained messages if kernel is tained.
        """
        self._logger.info("Checking for tained kernel")

        ret = self._sut.run_command(
            "cat /proc/sys/kernel/tainted",
            timeout=10)

        if ret["returncode"] != 0:
            raise DispatcherError("Error reading /proc/sys/kernel/tainted")

        tained_num = len(self.TAINED_MSG)

        code = int(ret["stdout"].rstrip())
        bits = format(code, f"0{tained_num}b")[::-1]

        messages = []
        for i in range(0, tained_num):
            if bits[i] == "1":
                msg = self.TAINED_MSG[i]
                messages.append(msg)

        self._logger.info("Tained kernel: %s", messages)

        return code, messages

    def _reboot_sut(self, force: bool = False) -> None:
        """
        This method reboot SUT if needed, for example, after a Kernel panic.
        """
        self._logger.info("Rebooting SUT")
        self._events.fire("sut_restart", self._sut.name)

        if force:
            self._sut.force_stop()
        else:
            self._sut.stop()

        self._sut.communicate()

        self._logger.info("SUT rebooted")

    def _save_dmesg(self, suite_name: str) -> None:
        """
        Save the current dmesg status inside temporary folder.
        """
        self._logger.info("Storing dmesg information")

        # read kernel messages for the current SUT instance
        dmesg_stdout = self._sut.run_command("dmesg", timeout=30)
        command = os.path.join(self._tmpdir, f"dmesg_{suite_name}.log")
        with open(command, "w", encoding="utf-8") as fdmesg:
            fdmesg.write(dmesg_stdout["stdout"])

    def _run_test(self, test: Test) -> TestResults:
        """
        Execute a test and return the results.
        """
        self._logger.info("Running test %s", test.name)
        self._logger.debug(test)

        self._events.fire("test_started", test)

        args = " ".join(test.arguments)
        cmd = f"{test.command} {args}"

        test_data = None

        # check for tained kernel status
        tained_code_before, tained_msg_before = self._check_tained()
        if tained_msg_before:
            for msg in tained_msg_before:
                self._events.fire("kernel_tained", msg)
                self._logger.debug("Kernel tained before test: %s", msg)

        timed_out = False
        reboot = False

        checker = KernelPanicChecker()
        try:
            test_data = self._sut.run_command(
                cmd,
                timeout=self._test_timeout,
                iobuffer=checker)
        except SUTTimeoutError:
            timed_out = True
            try:
                self._sut.run_command("test .", timeout=1)

                # SUT replies -> test timed out
                self._events.fire(
                    "test_timed_out",
                    test.name,
                    self._test_timeout)
            except SUTTimeoutError:
                reboot = True
                self._events.fire("sut_not_responding")
        except KernelPanicError:
            timed_out = True
            reboot = True
            self._events.fire("kernel_panic")
            self._logger.debug("Kernel panic recognized")

        # check again for tained kernel and if tained status has changed
        # just raise an exception and reboot the SUT
        tained_code_after, tained_msg_after = self._check_tained()
        if tained_code_before != tained_code_after:
            reboot = True
            for msg in tained_msg_after:
                self._events.fire("kernel_tained", msg)
                self._logger.debug("Kernel tained after test: %s", msg)

        if timed_out:
            test_data = {
                "name": test.name,
                "command": test.command,
                "stdout": checker.stdout,
                "returncode": -1,
                "exec_time": self._test_timeout,
            }

        results = self._get_test_results(
            test,
            test_data,
            timed_out=timed_out)

        self._events.fire("test_completed", results)

        self._logger.info("Test completed")
        self._logger.debug(results)

        if reboot:
            # reboot the system if it's not host
            if self._sut.name != "host":
                self._reboot_sut(force=True)

        return results

    # pylint: disable=too-many-locals
    def _run_suite(self, suite: Suite) -> SuiteResults:
        """
        Execute a specific testing suite and return the results.
        """
        self._logger.info("Running suite %s", suite.name)
        self._logger.debug(suite)

        # execute suite tests
        self._events.fire("suite_started", suite)

        start_t = time.time()
        tests_results = []

        for test in suite.tests:
            if self._stop:
                return None

            results = self._run_test(test)
            if not results:
                break

            tests_results.append(results)

            if time.time() - start_t >= self._suite_timeout:
                raise SuiteTimeoutError(
                    f"{suite.name} suite timed out "
                    f"(timeout={self._suite_timeout})")

        self._logger.info("Reading SUT information")

        # create suite results
        def _run_cmd(cmd: str) -> str:
            """
            Run command, check for returncode and return command's stdout.
            """
            ret = self._sut.run_command(cmd, timeout=10)
            if ret["returncode"] != 0:
                raise DispatcherError(f"Can't read information from SUT: {cmd}")

            stdout = ret["stdout"].rstrip()

            return stdout

        distro_str = _run_cmd(". /etc/os-release; echo \"$ID\"")
        distro_ver_str = _run_cmd(". /etc/os-release; echo \"$VERSION_ID\"")
        kernel_str = _run_cmd("uname -s -r -v")
        arch_str = _run_cmd("uname -m")

        suite_results = SuiteResults(
            suite=suite,
            tests=tests_results,
            distro=distro_str,
            distro_ver=distro_ver_str,
            kernel=kernel_str,
            arch=arch_str)

        # read kernel messages for the current SUT instance
        self._save_dmesg(suite.name)

        if suite_results:
            self._events.fire("suite_completed", suite_results)

        self._logger.debug(suite_results)
        self._logger.info("Suite completed")

        return suite_results

    def exec_suites(self, suites: list) -> list:
        if not suites:
            raise ValueError("Empty suites list")

        with self._exec_lock:
            # read available testing suites
            avail_suites = self._read_available_suites()

            if len(avail_suites) != len(suites) and \
                    set(avail_suites).issubset(set(suites)):
                raise DispatcherError(
                    "Some suites are not available. Available suites are: "
                    f"{' '.join(avail_suites)}")

            suites_obj = self._download_suites(suites)

            results = []
            for suite in suites_obj:
                result = self._run_suite(suite)
                if result:
                    results.append(result)

            return results
