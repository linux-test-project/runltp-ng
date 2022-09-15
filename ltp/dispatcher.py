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
import ltp.data
import ltp.events
from ltp import LTPException
from ltp.sut import IOBuffer
from ltp.sut import SUTTimeoutError
from ltp.data import Test
from ltp.data import Suite
from ltp.results import TestResults
from ltp.results import SuiteResults


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

    def exec_suites(self, suites: list, skip_tests: list = None) -> list:
        """
        Execute a list of testing suites.
        :param suites: list of Suite objects
        :type suites: list(str)
        :param skip_tests: list of tests to skip
        :type skip_tests: list(str)
        :returns: list(SuiteResults)
        """
        raise NotImplementedError()


class KernelPanicError(LTPException):
    """
    Raised during kernel panic.
    """


class StdoutChecker(IOBuffer):
    """
    Check for test's stdout and raise an exception if Kernel panic occured.
    """

    def __init__(self, test: Test) -> None:
        self.stdout = ""
        self._test = test
        self._line = ""

    def write(self, data: bytes) -> None:
        data_str = data.decode(encoding="utf-8", errors="replace")

        if len(data_str) == 1:
            self._line += data_str
            if data_str == "\n":
                ltp.events.fire(
                    "test_stdout_line",
                    self._test,
                    self._line[:-1])
                self._line = ""
        else:
            lines = data_str.split('\n')
            for line in lines[:-1]:
                self._line += line
                ltp.events.fire("test_stdout_line", self._test, self._line)
                self._line = ""

            self._line = lines[-1]

            if data_str.endswith('\n') and self._line:
                ltp.events.fire("test_stdout_line", self._test, self._line)
                self._line = ""

        self.stdout += data_str

        if "Kernel panic" in self.stdout:
            raise KernelPanicError()

    def flush(self) -> None:
        pass


class SerialDispatcher(Dispatcher):
    """
    Dispatcher implementation that serially runs test suites one after
    the other.
    """

    def __init__(self, **kwargs: dict) -> None:
        self._logger = logging.getLogger("ltp.dispatcher")
        self._ltpdir = kwargs.get("ltpdir", None)
        self._tmpdir = kwargs.get("tmpdir", None)
        self._sut = kwargs.get("sut", None)
        self._suite_timeout = max(kwargs.get("suite_timeout", 3600.0), 0.0)
        self._test_timeout = max(kwargs.get("test_timeout", 3600.0), 0.0)
        self._exec_lock = threading.Lock()
        self._stop = False

        if not self._ltpdir:
            raise ValueError("LTP directory doesn't exist")

        if not self._sut:
            raise ValueError("SUT object is empty")

        # create temporary directory where saving suites files
        self._tmpdir.mkdir("runtest")

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
                time.sleep(0.05)
                if time.time() - t_start >= t_secs:
                    raise DispatcherError("Timeout when stopping dispatcher")
        finally:
            self._stop = False

        self._logger.info("Dispatcher stopped")

    def _download_suites(self, suites: list) -> list:
        """
        Download all testing suites and return suites objects.
        """
        suites_obj = []

        for suite_name in suites:
            target = os.path.join(self._ltpdir, "runtest", suite_name)

            ltp.events.fire(
                "suite_download_started",
                suite_name,
                target)

            data = self._sut.fetch_file(target)
            data_str = data.decode(encoding="utf-8", errors="ignore")

            self._tmpdir.mkfile(os.path.join("runtest", suite_name), data_str)

            ltp.events.fire(
                "suite_download_completed",
                suite_name,
                target)

            suite = ltp.data.read_runtest(suite_name, data_str)
            suites_obj.append(suite)

        return suites_obj

    def _reboot_sut(self, force: bool = False) -> None:
        """
        This method reboot SUT if needed, for example, after a Kernel panic.
        """
        self._logger.info("Rebooting SUT")
        ltp.events.fire("sut_restart", self._sut.name)

        if force:
            self._sut.force_stop()
        else:
            self._sut.stop()

        self._sut.communicate()

        self._logger.info("SUT rebooted")

    def _run_test(self, test: Test) -> TestResults:
        """
        Execute a test and return the results.
        """
        self._logger.info("Running test %s", test.name)
        self._logger.debug(test)

        ltp.events.fire("test_started", test)

        args = " ".join(test.arguments)
        cmd = f"{test.command} {args}"

        test_data = None

        # check for tained kernel status
        tained_code_before, tained_msg_before = self._sut.get_tained_info()
        if tained_msg_before:
            for msg in tained_msg_before:
                ltp.events.fire("kernel_tained", msg)
                self._logger.debug("Kernel tained before test: %s", msg)

        timed_out = False
        reboot = False

        checker = StdoutChecker(test)
        try:
            test_data = self._sut.run_command(
                cmd,
                timeout=self._test_timeout,
                iobuffer=checker)
        except SUTTimeoutError:
            timed_out = True
            try:
                self._sut.ping()

                # SUT replies -> test timed out
                ltp.events.fire(
                    "test_timed_out",
                    test.name,
                    self._test_timeout)
            except SUTTimeoutError:
                reboot = True
                ltp.events.fire("sut_not_responding")
        except KernelPanicError:
            timed_out = True
            reboot = True
            ltp.events.fire("kernel_panic")
            self._logger.debug("Kernel panic recognized")

        if not reboot:
            # check again for tained kernel and if tained status has changed
            # just raise an exception and reboot the SUT
            tained_code_after, tained_msg_after = self._sut.get_tained_info()
            if tained_code_before != tained_code_after:
                reboot = True
                for msg in tained_msg_after:
                    ltp.events.fire("kernel_tained", msg)
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

        ltp.events.fire("test_completed", results)

        self._logger.info("Test completed")
        self._logger.debug(results)

        if reboot:
            # reboot the system if it's not host
            if self._sut.name != "host":
                self._reboot_sut(force=True)

        return results

    def _run_suite(
            self,
            suite: Suite,
            info: dict,
            skip_tests: list = None) -> SuiteResults:
        """
        Execute a specific testing suite and return the results.
        """
        self._logger.info("Running suite %s", suite.name)
        self._logger.debug(suite)

        # execute suite tests
        ltp.events.fire("suite_started", suite)

        start_t = time.time()
        tests_results = []

        for test in suite.tests:
            if self._stop:
                break

            if skip_tests and test.name in skip_tests:
                self._logger.info("Ignoring test: %s", test.name)
                continue

            results = self._run_test(test)
            if not results:
                break

            tests_results.append(results)

            if time.time() - start_t >= self._suite_timeout:
                raise SuiteTimeoutError(
                    f"{suite.name} suite timed out "
                    f"(timeout={self._suite_timeout})")

        if not tests_results:
            # no tests execution means no suite
            return None

        suite_results = SuiteResults(
            suite=suite,
            tests=tests_results,
            distro=info["distro"],
            distro_ver=info["distro_ver"],
            kernel=info["kernel"],
            arch=info["arch"],
            cpu=info["cpu"],
            swap=info["swap"],
            ram=info["ram"])

        if suite_results:
            ltp.events.fire("suite_completed", suite_results)

        self._logger.debug(suite_results)
        self._logger.info("Suite completed")

        return suite_results

    def exec_suites(self, suites: list, skip_tests: list = None) -> list:
        if not suites:
            raise ValueError("Empty suites list")

        with self._exec_lock:
            suites_obj = self._download_suites(suites)

            info = self._sut.get_info()

            results = []
            for suite in suites_obj:
                result = self._run_suite(suite, info, skip_tests=skip_tests)

                if result:
                    results.append(result)

            return results
