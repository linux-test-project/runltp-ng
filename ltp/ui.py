"""
.. module:: ui
    :platform: Linux
    :synopsis: module that contains user interface

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import platform
import traceback
import ltp.events
from ltp.data import Test
from ltp.data import Suite
from ltp.results import TestResults
from ltp.results import SuiteResults

# pylint: disable=too-many-public-methods
# pylint: disable=missing-function-docstring
# pylint: disable=unused-argument


class ConsoleUserInterface:
    """
    Console based user interface.
    """

    GREEN = "\033[1;32m"
    YELLOW = "\033[1;33m"
    RED = "\033[1;31m"
    CYAN = "\033[1;36m"
    RESET = "\033[2J"

    def __init__(self, colors_rule: str = "default") -> None:
        self._colors_rule = colors_rule

    def _print(self, msg: str, color: str = None, end: str = "\n"):
        """
        Print a message.
        """
        if color and self._colors_rule != "none":
            print(color + msg + '\033[0m', end=end)
        else:
            print(msg, end=end)


class SimpleUserInterface(ConsoleUserInterface):
    """
    Console based user interface without many fancy stuff.
    """

    def __init__(self, colors_rule: str = "default") -> None:
        super().__init__(colors_rule=colors_rule)

        self._sut_not_responding = False
        self._kernel_panic = False
        self._kernel_tained = None
        self._timed_out = False

        ltp.events.register("session_started", self.session_started)
        ltp.events.register("session_stopped", self.session_stopped)
        ltp.events.register("session_error", self.session_error)
        ltp.events.register("sut_start", self.sut_start)
        ltp.events.register("sut_stop", self.sut_stop)
        ltp.events.register("sut_restart", self.sut_restart)
        ltp.events.register("sut_not_responding", self.sut_not_responding)
        ltp.events.register("kernel_panic", self.kernel_panic)
        ltp.events.register("kernel_tained", self.kernel_tained)
        ltp.events.register("test_timed_out", self.test_timed_out)
        ltp.events.register("suite_download_started",
                            self.suite_download_started)
        ltp.events.register("suite_started", self.suite_started)
        ltp.events.register("suite_completed", self.suite_completed)
        ltp.events.register("test_started", self.test_started)
        ltp.events.register("test_completed", self.test_completed)
        ltp.events.register("run_cmd_start", self.run_cmd_start)
        ltp.events.register("run_cmd_stop", self.run_cmd_stop)

    def session_started(self, tmpdir: str) -> None:
        uname = platform.uname()
        message = "Host information\n\n"
        message += f"\tSystem: {uname.system}\n"
        message += f"\tNode: {uname.node}\n"
        message += f"\tKernel Release: {uname.release}\n"
        message += f"\tKernel Version: {uname.version}\n"
        message += f"\tMachine Architecture: {uname.machine}\n"
        message += f"\tProcessor: {uname.processor}\n"
        message += f"\n\tTemporary directory: {tmpdir}\n"

        self._print(message)

    def session_stopped(self) -> None:
        self._print("Session stopped")

    def session_error(self, error: str) -> None:
        self._print(f"Error: {error}")

    def sut_start(self, sut: str) -> None:
        self._print(f"Connecting to SUT: {sut}")

    def sut_stop(self, sut: str) -> None:
        self._print(f"\nDisconnecting from SUT: {sut}")

    def sut_restart(self, sut: str) -> None:
        self._print(f"Restarting SUT: {sut}")

    def sut_not_responding(self) -> None:
        self._sut_not_responding = True

    def kernel_panic(self) -> None:
        self._kernel_panic = True

    def kernel_tained(self, message: str) -> None:
        self._kernel_tained = message

    def test_timed_out(self, _: Test, timeout: int) -> None:
        self._timed_out = True

    def suite_download_started(
            self,
            name: str,
            target: str) -> None:
        self._print(f"Downloading suite: {name}")

    def suite_started(self, suite: Suite) -> None:
        self._print(f"Starting suite: {suite.name}")

    def suite_completed(self, results: SuiteResults) -> None:
        message = "\n"
        message += f"Suite Name: {results.suite.name}\n"
        message += f"Total Run: {len(results.suite.tests)}\n"
        message += f"Elapsed Time: {results.exec_time:.1f} seconds\n"
        message += f"Passed Tests: {results.passed}\n"
        message += f"Failed Tests: {results.failed}\n"
        message += f"Skipped Tests: {results.skipped}\n"
        message += f"Broken Tests: {results.broken}\n"
        message += f"Warnings: {results.warnings}\n"
        message += f"Kernel Version: {results.kernel}\n"
        message += f"CPU: {results.cpu}\n"
        message += f"Machine Architecture: {results.arch}\n"
        message += f"RAM: {results.ram}\n"
        message += f"Swap memory: {results.swap}\n"
        message += f"Distro: {results.distro}\n"
        message += f"Distro Version: {results.distro_ver}\n"

        self._print(message)

    def test_started(self, test: Test) -> None:
        self._print(f"{test.name}: ", end="")

    def test_completed(self, results: TestResults) -> None:
        if self._timed_out:
            self._print("timed out", color=self.RED)
        elif self._sut_not_responding:
            # this message will replace ok/fail message
            self._print("SUT not responding", color=self.RED)
        elif self._kernel_panic:
            # this message will replace ok/fail message
            self._print("kernel panic", color=self.RED)
        else:
            msg = "pass"
            col = self.GREEN

            if results.failed > 0:
                msg = "fail"
                col = self.RED
            elif results.skipped > 0:
                msg = "skip"
                col = self.YELLOW
            elif results.broken > 0:
                msg = "broken"
                col = self.CYAN

            self._print(msg, color=col, end="")

            if self._kernel_tained:
                self._print(" | ", end="")
                self._print("tained", color=self.YELLOW)
            else:
                self._print("")

        self._sut_not_responding = False
        self._kernel_panic = False
        self._kernel_tained = None
        self._timed_out = False

    def run_cmd_start(self, cmd: str) -> None:
        self._print(f"{cmd} ", end="", color=self.CYAN)

    def run_cmd_stop(self, command: str, stdout: str, returncode: int) -> None:
        self._print(f"(exit_code {returncode}", end="")

        if "TFAIL" in stdout:
            self._print(" TFAIL", color=self.RED, end="")
        elif "TSKIP" in stdout:
            self._print(" TSKIP", color=self.YELLOW, end="")
        elif "TCONF" in stdout:
            self._print(" TCONF", color=self.YELLOW, end="")
        elif "TBROK" in stdout:
            self._print(" TBROK", color=self.CYAN, end="")
        elif "TPASS" in stdout:
            self._print(" TPASS", color=self.GREEN, end="")

        self._print(")")


class VerboseUserInterface(ConsoleUserInterface):
    """
    Verbose console based user interface.
    """

    def __init__(self, colors_rule: str = "default") -> None:
        super().__init__(colors_rule=colors_rule)

        self._timed_out = False
        self._buffer = ""

        ltp.events.register("session_started", self.session_started)
        ltp.events.register("session_stopped", self.session_stopped)
        ltp.events.register("session_error", self.session_error)
        ltp.events.register("sut_start", self.sut_start)
        ltp.events.register("sut_stop", self.sut_stop)
        ltp.events.register("sut_restart", self.sut_restart)
        ltp.events.register("sut_stdout_line", self.sut_stdout_line)
        ltp.events.register("kernel_tained", self.kernel_tained)
        ltp.events.register("test_timed_out", self.test_timed_out)
        ltp.events.register("suite_download_started",
                            self.suite_download_started)
        ltp.events.register("suite_started", self.suite_started)
        ltp.events.register("suite_completed", self.suite_completed)
        ltp.events.register("test_started", self.test_started)
        ltp.events.register("test_completed", self.test_completed)
        ltp.events.register("test_stdout_line", self.test_stdout_line)
        ltp.events.register("run_cmd_start", self.run_cmd_start)
        ltp.events.register("run_cmd_stdout", self.run_cmd_stdout)
        ltp.events.register("run_cmd_stop", self.run_cmd_stop)

    def session_started(self, tmpdir: str) -> None:
        uname = platform.uname()
        message = "Host information\n\n"
        message += f"\tSystem: {uname.system}\n"
        message += f"\tNode: {uname.node}\n"
        message += f"\tKernel Release: {uname.release}\n"
        message += f"\tKernel Version: {uname.version}\n"
        message += f"\tMachine Architecture: {uname.machine}\n"
        message += f"\tProcessor: {uname.processor}\n"
        message += f"\n\tTemporary directory: {tmpdir}\n"

        self._print(message)

    def session_stopped(self) -> None:
        self._print("Session stopped")

    def session_error(self, error: str) -> None:
        message = f"Error: {error}"

        trace = traceback.format_exc()
        if trace:
            message += f"\n\n{trace}"

        self._print(message)

    def sut_start(self, sut: str) -> None:
        self._print(f"Connecting to SUT: {sut}")

    def sut_stop(self, sut: str) -> None:
        self._print(f"\nDisconnecting from SUT: {sut}")

    def sut_restart(self, sut: str) -> None:
        self._print(f"Restarting SUT: {sut}")

    def sut_stdout_line(self, _: str, data: bytes) -> None:
        self._buffer += data.decode(encoding="utf-8", errors="ignore")

        if data == b'\n':
            # remove reset character, otherwise terminal logs might be cleaned
            self._buffer = self._buffer.replace(self.RESET, "")
            self._print(self._buffer, end="")
            self._buffer = ""

    def kernel_tained(self, message: str) -> None:
        self._print(f"Tained kernel: {message}", color=self.YELLOW)

    def test_timed_out(self, _: Test, timeout: int) -> None:
        self._timed_out = True

    def suite_download_started(
            self,
            name: str,
            target: str) -> None:
        self._print(f"Downloading suite: {target}")

    def suite_started(self, suite: Suite) -> None:
        self._print(f"Starting suite: {suite.name}")

    def suite_completed(self, results: SuiteResults) -> None:
        message = "\n"
        message += f"Suite Name: {results.suite.name}\n"
        message += f"Total Run: {len(results.suite.tests)}\n"
        message += f"Elapsed Time: {results.exec_time:.1f} seconds\n"
        message += f"Passed Tests: {results.passed}\n"
        message += f"Failed Tests: {results.failed}\n"
        message += f"Skipped Tests: {results.skipped}\n"
        message += f"Broken Tests: {results.broken}\n"
        message += f"Warnings: {results.warnings}\n"
        message += f"Kernel Version: {results.kernel}\n"
        message += f"CPU: {results.cpu}\n"
        message += f"Machine Architecture: {results.arch}\n"
        message += f"RAM: {results.ram}\n"
        message += f"Swap memory: {results.swap}\n"
        message += f"Distro: {results.distro}\n"
        message += f"Distro Version: {results.distro_ver}\n"

        self._print(message)

    def test_started(self, test: Test) -> None:
        self._print(f"running {test.name}")

    def test_completed(self, results: TestResults) -> None:
        if self._timed_out:
            self._print("Test timed out", color=self.RED)

        self._timed_out = False

    def test_stdout_line(self, _: Test, line: str) -> None:
        col = ""

        if self._colors_rule == "default":
            if "TPASS" in line:
                col = self.GREEN
            elif "TFAIL" in line:
                col = self.RED
            elif "TSKIP" in line:
                col = self.YELLOW
            elif "TCONF" in line:
                col = self.CYAN
            elif "Kernel panic" in line:
                col = self.RED

        self._print(line, color=col)

    def run_cmd_start(self, cmd: str) -> None:
        self._print(f"{cmd}\n", end="", color=self.CYAN)

    def run_cmd_stdout(self, data: bytes) -> None:
        self._print(data.decode(encoding="utf-8", errors="ignore"))

    def run_cmd_stop(self, command: str, stdout: str, returncode: int) -> None:
        msg = f"\nExit code: {returncode}"
        self._print(msg)
