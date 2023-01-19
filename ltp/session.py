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
import ltp
from ltp import LTPException
from ltp.sut import SUT
from ltp.sut import IOBuffer
from ltp.tempfile import TempDir
from ltp.dispatcher import SerialDispatcher
from ltp.dispatcher import SuiteTimeoutError
from ltp.export import JSONExporter
from ltp.utils import Timeout


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

    def write(self, data: str) -> None:
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
    RC_TIMEOUT = 124
    RC_INTERRUPT = 130

    def __init__(self, **kwargs) -> None:
        """
        :param tmpdir: temporary directory path
        :type tmpdir: str
        :param ltpdir: LTP directory path
        :type ltpdir: str
        :param sut: SUT communication object
        :type sut: SUT
        :param sut_config: SUT object configuration
        :type sut_config: dict
        :param no_colors: if True, it disables LTP tests colors
        :type no_colors: bool
        :param exec_timeout: test timeout
        :type exec_timeout: float
        :param suite_timeout: testing suite timeout
        :type suite_timeout: float
        :param skip_tests: regexp excluding tests from execution
        :type skip_tests: str
        :param env: SUT environment vairables to inject before execution
        :type env: dict
        """
        self._logger = logging.getLogger("ltp.session")
        self._tmpdir = TempDir(kwargs.get("tmpdir", "/tmp"))
        self._ltpdir = kwargs.get("ltpdir", "/opt/ltp")
        self._sut = kwargs.get("sut", None)
        self._no_colors = kwargs.get("no_colors", False)
        self._env = kwargs.get("env", None)
        self._exec_timeout = max(kwargs.get("exec_timeout", 3600.0), 0.0)
        self._suite_timeout = max(kwargs.get("suite_timeout", 3600.0), 0.0)
        self._skip_tests = kwargs.get("skip_tests", "")

        self._sut_config = self._get_sut_config(kwargs.get("sut_config", {}))
        self._setup_debug_log()

        self._lock_run = threading.Lock()
        self._dispatcher = SerialDispatcher(
            ltpdir=self._ltpdir,
            tmpdir=self._tmpdir,
            sut=self._sut,
            suite_timeout=self._suite_timeout,
            test_timeout=self._exec_timeout)

    def _setup_debug_log(self) -> None:
        """
        Set logging module so we save a log file with debugging information
        inside the temporary path.
        """
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)

        debug_file = os.path.join(self._tmpdir.abspath, "debug.log")
        handler = logging.FileHandler(debug_file, encoding="utf8")
        handler.setLevel(logging.DEBUG)

        formatter = logging.Formatter(
            "%(asctime)s - %(name)s:%(lineno)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    def _get_sut_config(self, sut_config: dict) -> dict:
        """
        Create the SUT configuration. The dictionary is usually passed to the
        `setup` method of the SUT, in order to setup the environment before
        running tests.
        """
        testcases = os.path.join(self._ltpdir, "testcases", "bin")

        env = {}
        env["PATH"] = "/sbin:/usr/sbin:/usr/local/sbin:" + \
            f"/root/bin:/usr/local/bin:/usr/bin:/bin:{testcases}"
        env["LTPROOT"] = self._ltpdir
        env["TMPDIR"] = self._tmpdir.root if self._tmpdir.root else "/tmp"
        env["LTP_TIMEOUT_MUL"] = str((self._exec_timeout * 0.9) / 300.0)

        if self._no_colors:
            env["LTP_COLORIZE_OUTPUT"] = "0"
        else:
            env["LTP_COLORIZE_OUTPUT"] = "1"

        if self._env:
            for key, value in self._env.items():
                if key in env:
                    continue

                self._logger.info("Set environment variable %s=%s", key, value)
                env[key] = value

        config = sut_config.copy()
        config['env'] = env
        config['cwd'] = testcases
        config['tmpdir'] = self._tmpdir.abspath

        return config

    def _start_sut(self) -> None:
        """
        Start a new SUT and return it initialized.
        """
        testcases = os.path.join(self._ltpdir, "testcases", "bin")

        sut_env = {}
        sut_env["PATH"] = "/sbin:/usr/sbin:/usr/local/sbin:" + \
            f"/root/bin:/usr/local/bin:/usr/bin:/bin:{testcases}"
        sut_env["LTPROOT"] = self._ltpdir
        sut_env["TMPDIR"] = self._tmpdir.root if self._tmpdir.root else "/tmp"
        sut_env["LTP_TIMEOUT_MUL"] = str((self._exec_timeout * 0.9) / 300.0)

        if self._no_colors:
            sut_env["LTP_COLORIZE_OUTPUT"] = "0"
        else:
            sut_env["LTP_COLORIZE_OUTPUT"] = "1"

        if self._env:
            for key, value in self._env.items():
                if key not in sut_env:
                    self._logger.info(
                        "Add %s=%s environment variable into SUT")
                    sut_env[key] = value

        config = {}
        config['env'] = sut_env
        config['cwd'] = testcases
        config['tmpdir'] = self._tmpdir.abspath
        config.update(self._sut_config)

        self._sut.setup(**config)

        ltp.events.fire("sut_start", self._sut.name)

        self._sut.ensure_communicate(
            timeout=3600,
            iobuffer=Printer(self._sut, False))

    def _stop_sut(self, timeout: float = 30) -> None:
        """
        Stop a specific SUT.
        """
        if not self._sut.is_running:
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

    def _stop_all(self, timeout: float = 30) -> None:
        """
        Stop both sut and dispatcher.
        """
        if self._dispatcher:
            self._dispatcher.stop(timeout=timeout)

        self._stop_sut(timeout=timeout)

    def stop(self, timeout: float = 30) -> None:
        """
        Stop the current running session.
        """
        self._logger.info("Stopping session")

        with Timeout(timeout) as timer:
            self._stop_all(timeout=timeout)
            ltp.events.fire("session_stopped")

            timer.check(err_msg="Timeout when stopping session")

            while self._lock_run.locked():
                time.sleep(1e-6)
                timer.check(
                    err_msg="Timeout when stopping session",
                    exc=SessionError)

        self._logger.info("Session stopped")

    def run_single(
            self,
            command: str = None,
            suites: list = None,
            report_path: str = None) -> int:
        """
        Run some testing suites with a specific SUT configurations.
        :param command: command to execute
        :type command: str
        :param suites: suites to execute
        :type suites: list
        :param report_path: path of the report file. If None, it won't be saved
        :type report_path: None | str
        :returns: exit code for the session
        """
        exit_code = self.RC_OK

        with self._lock_run:
            ltp.events.fire("session_started", self._tmpdir.abspath)

            try:
                self._start_sut()

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
                    self._dispatcher.exec_suites(
                        suites, skip_tests=self._skip_tests)

                    self._dispatcher.stop()
            except SuiteTimeoutError:
                exit_code = self.RC_TIMEOUT
            except LTPException as err:
                self._stop_all(timeout=60)

                self._logger.exception(err)
                ltp.events.fire("session_error", str(err))

                exit_code = self.RC_ERROR
            except KeyboardInterrupt:
                self._logger.info("Keyboard interrupt")
                self._stop_all(timeout=60)
                ltp.events.fire("session_stopped")

                exit_code = self.RC_INTERRUPT
            finally:
                results = self._dispatcher.last_results
                if results:
                    exporter = JSONExporter()

                    if self._tmpdir.abspath:
                        # store JSON report in the temporary folder
                        results_report = os.path.join(
                            self._tmpdir.abspath,
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
