"""
.. module:: dispatcher
    :platform: Linux
    :synopsis: module containing Dispatcher definition and implementation.

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import re
import sys
import time
import logging
import threading
import ltp
import ltp.data
from ltp import LTPException
from ltp.sut import SUT
from ltp.sut import IOBuffer
from ltp.sut import SUTTimeoutError
from ltp.sut import KernelPanicError
from ltp.data import Test
from ltp.data import Suite
from ltp.results import TestResults
from ltp.results import SuiteResults
from ltp.utils import Timeout


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

        # get rid of colors from stdout
        stdout = re.sub(r'\u001b\[[0-9;]+[a-zA-Z]', '', stdout)

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
                if retcode == 0:
                    passed = 1
                elif retcode == 4:
                    warnings = 1
                elif retcode == 32:
                    skipped = 1
                else:
                    failed = 1

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

    @property
    def last_results(self) -> list:
        """
        Last testing suites results.
        :returns: list(SuiteResults)
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


class StdoutChecker(IOBuffer):
    """
    Check for test's stdout and raise an exception if Kernel panic occured.
    """

    def __init__(self, test: Test) -> None:
        self.stdout = ""
        self._test = test
        self._line = ""

    def write(self, data: str) -> None:
        if len(data) == 1:
            self._line += data
            if data == "\n":
                ltp.events.fire(
                    "test_stdout_line",
                    self._test,
                    self._line[:-1])
                self._line = ""
        else:
            lines = data.split('\n')
            for line in lines[:-1]:
                self._line += line
                ltp.events.fire("test_stdout_line", self._test, self._line)
                self._line = ""

            self._line = lines[-1]

            if data.endswith('\n') and self._line:
                ltp.events.fire("test_stdout_line", self._test, self._line)
                self._line = ""

        self.stdout += data

    def flush(self) -> None:
        pass


class RedirectStdout(IOBuffer):
    """
    Redirect data from stdout to events.
    """

    def __init__(self, sut: SUT) -> None:
        self._sut = sut

    def write(self, data: str) -> None:
        if not self._sut:
            return

        ltp.events.fire("sut_stdout_line", self._sut.name, data)

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
        self._last_results = None

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

    @property
    def last_results(self) -> list:
        return self._last_results

    def stop(self, timeout: float = 30) -> None:
        if not self.is_running:
            return

        self._logger.info("Stopping dispatcher")

        self._stop = True

        try:
            with Timeout(timeout) as timer:
                while self.is_running:
                    time.sleep(0.05)
                    timer.check(
                        err_msg="Timeout when stopping dispatcher",
                        exc=DispatcherError)
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
            self._sut.force_stop(timeout=360)
        else:
            self._sut.stop(timeout=360)

        self._sut.ensure_communicate(
            timeout=3600,
            iobuffer=RedirectStdout(self._sut),
            force=force)

        self._logger.info("SUT rebooted")

    def _write_kmsg(self, test: Test) -> None:
        """
        If root, we write test information on /dev/kmsg.
        """
        self._logger.info("Writing test information on /dev/kmsg")

        ret = self._sut.run_command("id -u", timeout=10)
        if ret["stdout"] != "0\n":
            self._logger.info("Can't write on /dev/kmsg from user")
            return

        cmd = f"{test.command}"
        if len(test.arguments) > 0:
            cmd += ' '
            cmd += ' '.join(test.arguments)

        message = f'{sys.argv[0]}[{os.getpid()}]: ' \
            f'starting test {test.name} ({cmd})\n'

        self._sut.run_command(f'echo -n "{message}" > /dev/kmsg', timeout=10)

    def _run_test(self, test: Test) -> TestResults:
        """
        Execute a test and return the results.
        """
        self._logger.info("Running test %s", test.name)
        self._logger.debug(test)

        ltp.events.fire("test_started", test)

        self._write_kmsg(test)

        args = " ".join(test.arguments)
        cmd = f"{test.command} {args}"

        test_data = None

        # check for tainted kernel status
        tainted_code_before, tainted_msg_before = self._sut.get_tainted_info()
        if tainted_msg_before:
            for msg in tainted_msg_before:
                ltp.events.fire("kernel_tainted", msg)
                self._logger.debug("Kernel tainted before test: %s", msg)

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
            # check again for tainted kernel and if tainted status has changed
            # just raise an exception and reboot the SUT
            tainted_code_after, tainted_msg_after = \
                self._sut.get_tainted_info()
            if tainted_code_before != tainted_code_after:
                reboot = True
                for msg in tainted_msg_after:
                    ltp.events.fire("kernel_tainted", msg)
                    self._logger.debug("Kernel tainted after test: %s", msg)

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
            skip_tests: str = None) -> None:
        """
        Execute a specific testing suite and return the results.
        """
        self._logger.info("Running suite %s", suite.name)
        self._logger.debug(suite)

        # execute suite tests
        ltp.events.fire("suite_started", suite)

        start_t = time.time()
        tests_results = []
        timed_out = False
        interrupt = False

        for test in suite.tests:
            if self._stop:
                break

            if timed_out or interrupt:
                # after suite timeout treat all tests left as skipped tests
                result = TestResults(
                    test=test,
                    failed=0,
                    passed=0,
                    broken=0,
                    skipped=1,
                    warnings=0,
                    exec_time=0.0,
                    retcode=32,
                    stdout="",
                )
                tests_results.append(result)
                continue

            if skip_tests and re.search(skip_tests, test.name):
                self._logger.info("Ignoring test: %s", test.name)
                continue

            try:
                results = self._run_test(test)
                if results:
                    tests_results.append(results)
            except KeyboardInterrupt:
                # catch SIGINT during test execution and postpone it after
                # results have been collected, so we don't loose tests reports
                interrupt = True

            if time.time() - start_t >= self._suite_timeout:
                timed_out = True

        if not tests_results:
            # no tests execution means no suite
            return

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

        self._last_results.append(suite_results)

        if suite_results:
            ltp.events.fire("suite_completed", suite_results)

        self._logger.debug(suite_results)
        self._logger.info("Suite completed")

        if interrupt:
            raise KeyboardInterrupt()

        if timed_out:
            self._logger.info("Testing suite timed out: %s", suite.name)

            ltp.events.fire(
                "suite_timeout",
                suite,
                self._suite_timeout)

            raise SuiteTimeoutError(
                f"{suite.name} suite timed out "
                f"(timeout={self._suite_timeout})")

    def exec_suites(self, suites: list, skip_tests: str = None) -> list:
        if not suites:
            raise ValueError("Empty suites list")

        with self._exec_lock:
            self._last_results = []

            suites_obj = self._download_suites(suites)
            info = self._sut.get_info()

            for suite in suites_obj:
                self._run_suite(suite, info, skip_tests=skip_tests)

            return self._last_results
