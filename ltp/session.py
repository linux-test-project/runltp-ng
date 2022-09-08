"""
.. module:: session
    :platform: Linux
    :synopsis: module that contains LTP session definition

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import time
import logging
import threading
import ltp.events
from ltp import LTPException
from ltp.sut import SUT
from ltp.sut import IOBuffer
from ltp.qemu import QemuSUT
from ltp.host import HostSUT
from ltp.ssh import SSHSUT
from ltp.results import SuiteResults
from ltp.tempfile import TempDir
from ltp.dispatcher import SerialDispatcher
from ltp.dispatcher import SuiteTimeoutError
from ltp.export import JSONExporter


class SessionError(LTPException):
    """
    Raised when a new exception occurs during session.
    """


class Printer(IOBuffer):
    """
    Redirect data from stdout to events.
    """

    def __init__(self, sut: SUT, is_cmd: bool) -> None:
        self._sut = sut
        self._is_cmd = is_cmd

    def write(self, data: bytes) -> None:
        if self._is_cmd:
            ltp.events.fire("run_cmd_stdout", data)
        else:
            ltp.events.fire("sut_stdout_line", self._sut.name, data)

    def flush(self) -> None:
        pass


class Session:
    """
    The main session handler.
    """

    RC_OK = 0
    RC_ERROR = 1
    RC_INTERRUPT = 2
    RC_TIMEOUT = 4

    def __init__(
            self,
            suite_timeout: float = 3600,
            exec_timeout: float = 3600,
            no_colors: bool = False) -> None:
        """
        :param suite_timeout: timeout before stopping testing suite
        :type suite_timeout: float
        :param exec_timeout: timeout before stopping single execution
        :type exec_timeout: float
        :param no_colors: disable LTP colors
        :type no_colors: bool
        """
        self._logger = logging.getLogger("ltp.session")
        self._suite_timeout = max(suite_timeout, 0)
        self._exec_timeout = max(exec_timeout, 0)
        self._sut = None
        self._dispatcher = None
        self._lock_run = threading.Lock()
        self._no_colors = no_colors

    @staticmethod
    def _setup_debug_log(tmpdir: TempDir) -> None:
        """
        Save a log file with debugging information
        """
        if not tmpdir.abspath:
            return

        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)

        debug_file = os.path.join(tmpdir.abspath, "debug.log")
        handler = logging.FileHandler(debug_file, encoding="utf8")
        handler.setLevel(logging.DEBUG)

        formatter = logging.Formatter(
            "%(asctime)s - %(name)s:%(lineno)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    def _print_results(self, suite_results: SuiteResults) -> None:
        """
        Print suite results.
        """
        tests = len(suite_results.tests_results)

        self._logger.info("")
        self._logger.info("Suite name: %s", suite_results.suite.name)
        self._logger.info("Total Run: %d", tests)
        self._logger.info("Elapsed time: %.1f s", suite_results.exec_time)
        self._logger.info("Total Passed Tests: %d", suite_results.passed)
        self._logger.info("Total Failed Tests: %d", suite_results.failed)
        self._logger.info("Total Skipped Tests: %d", suite_results.skipped)
        self._logger.info("Total Broken Tests: %d", suite_results.broken)
        self._logger.info("Total Warnings: %d", suite_results.warnings)
        self._logger.info("Kernel Version: %s", suite_results.kernel)
        self._logger.info("Machine Architecture: %s", suite_results.arch)
        self._logger.info("Distro: %s", suite_results.distro)
        self._logger.info("Distro version: %s", suite_results.distro_ver)
        self._logger.info("")

    def _start_sut(
            self,
            ltpdir: str,
            tmpdir: TempDir,
            sut_config: dict) -> SUT:
        """
        Start a new SUT and return it initialized.
        """
        sut_name = sut_config.pop("name", None)
        if sut_name not in ["qemu", "host", "ssh"]:
            raise ValueError(f"{sut_name} is not supported")

        testcases = os.path.join(ltpdir, "testcases", "bin")

        env = {}
        env["PATH"] = "/sbin:/usr/sbin:/usr/local/sbin:" + \
            f"/root/bin:/usr/local/bin:/usr/bin:/bin:{testcases}"
        env["LTPROOT"] = ltpdir
        env["TMPDIR"] = tmpdir.root if tmpdir.root else "/tmp"
        env["LTP_TIMEOUT_MUL"] = str((self._exec_timeout * 0.9) / 300.0)

        if self._no_colors:
            env["LTP_COLORIZE_OUTPUT"] = "0"
        else:
            env["LTP_COLORIZE_OUTPUT"] = "1"

        config = {}
        config['env'] = env
        config['cwd'] = testcases
        config['tmpdir'] = tmpdir.abspath
        config.update(sut_config)

        sut = None
        timeout = 0.0

        if sut_name == 'qemu':
            sut = QemuSUT(**config)
            timeout = 360.0
        elif sut_name == 'ssh':
            sut = SSHSUT(**config)
            timeout = 360.0
        else:
            sut = HostSUT(cwd=ltpdir, env=env)
            timeout = 10.0

        ltp.events.fire("sut_start", sut.name)

        sut.communicate(
            timeout=timeout,
            iobuffer=Printer(sut, False))

        return sut

    def _stop_sut(self, timeout: float = 30) -> None:
        """
        Stop a specific SUT.
        """
        if not self._sut:
            return

        ltp.events.fire("sut_stop", self._sut.name)

        if self._sut.is_running:
            self._sut.stop(
                timeout=timeout,
                iobuffer=Printer(self._sut, False))
        else:
            self._sut.force_stop(
                timeout=timeout,
                iobuffer=Printer(self._sut, False))

        self._sut = None

    def _stop_all(self, timeout: float = 30) -> None:
        """
        Stop both sut and dispatcher.
        """
        if not self._sut:
            return

        if self._dispatcher:
            self._dispatcher.stop(timeout=timeout)

        self._stop_sut(timeout=timeout)

    def stop(self, timeout: float = 30):
        """
        Stop the current running session.
        """
        if not self._sut:
            return

        self._logger.info("Stopping session")

        self._stop_all(timeout=timeout)
        ltp.events.fire("session_stopped")

        t_start = time.time()
        while self._lock_run.locked():
            time.sleep(0.05)
            if time.time() - t_start >= timeout:
                raise SessionError("Timeout when stopping session")

        self._logger.info("Session stopped")

    # pylint: disable=too-many-locals
    # pylint: disable=too-many-statements
    # pylint: disable=too-many-arguments
    def run_single(
            self,
            sut_config: dict,
            report_path: str,
            suites: list,
            command: str,
            ltpdir: str,
            tmpdir: TempDir,
            skip_tests: str = None) -> int:
        """
        Run some testing suites with a specific SUT configurations.
        :param sut_config: system under test configuration.
        :type sut_config: dict
        :param report_path: path of the report file. If None, it won't be saved
        :type report_path: None | str
        :param suites: suites to execute
        :type suites: list
        :param command: command to execute
        :type command: str
        :param ltpdir: ltp install folder
        :type ltpdir: str
        :param tmpdir: temporary directory
        :type tmpdir: TempDir
        :param skip_tests: tests to ignore in a regex form
        :type skip_tests: str
        :returns: exit code for the session
        """
        if not sut_config:
            raise ValueError("sut configuration can't be empty")

        exit_code = self.RC_OK

        with self._lock_run:
            self._sut = None
            self._dispatcher = None

            self._logger.info(
                "Running session using temporary folder: %s",
                tmpdir.abspath)

            self._setup_debug_log(tmpdir)
            ltp.events.fire("session_started", tmpdir.abspath)

            try:
                self._sut = self._start_sut(
                    ltpdir,
                    tmpdir,
                    sut_config)

                self._logger.info("Created SUT: %s", self._sut.name)

                if command:
                    ltp.events.fire("run_cmd_start", command)

                    ret = self._sut.run_command(
                        command,
                        timeout=self._exec_timeout,
                        iobuffer=Printer(self._sut, True))

                    ltp.events.fire(
                        "run_cmd_stop",
                        command,
                        ret["stdout"],
                        ret["returncode"])

                if suites:
                    self._dispatcher = SerialDispatcher(
                        ltpdir=ltpdir,
                        tmpdir=tmpdir,
                        sut=self._sut,
                        suite_timeout=self._suite_timeout,
                        test_timeout=self._exec_timeout)

                    self._logger.info("Created dispatcher")

                    self._dispatcher.exec_suites(
                        suites, skip_tests=skip_tests)

                    self._dispatcher.stop()
            except SuiteTimeoutError:
                exit_code = self.RC_TIMEOUT
            except LTPException as err:
                self._stop_all(timeout=60)

                self._logger.error("Error: %s", str(err))
                ltp.events.fire("session_error", str(err))

                exit_code = self.RC_ERROR
            except KeyboardInterrupt:
                self._logger.info("Keyboard interrupt")
                self._stop_all(timeout=60)
                ltp.events.fire("session_stopped")

                exit_code = self.RC_INTERRUPT
            finally:
                if not self._dispatcher:
                    self._stop_sut(timeout=60)
                else:
                    results = self._dispatcher.last_results
                    if results:
                        for result in results:
                            self._print_results(result)

                        exporter = JSONExporter()

                        if tmpdir.abspath:
                            # store JSON report in the temporary folder
                            results_report = os.path.join(
                                tmpdir.abspath,
                                "results.json")

                            exporter.save_file(results, results_report)

                        if report_path:
                            exporter.save_file(results, report_path)

                    if not suites or (results and len(suites) == len(results)):
                        # session has not been stopped
                        self._stop_sut(timeout=60)
                        ltp.events.fire("session_completed", results)
                        self._logger.info("Session completed")

        return exit_code
