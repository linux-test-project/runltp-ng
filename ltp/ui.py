"""
.. module:: ui
    :platform: Linux
    :synopsis: module that contains user interface

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import platform
import ltp
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
    RESET_COLOR = "\033[0m"
    RESET_SCREEN = "\033[2J"

    def __init__(self, no_colors: bool = False) -> None:
        self._no_colors = no_colors
        self._line = ""

        ltp.events.register("session_started", self.session_started)
        ltp.events.register("session_stopped", self.session_stopped)
        ltp.events.register("sut_start", self.sut_start)
        ltp.events.register("sut_stop", self.sut_stop)
        ltp.events.register("sut_restart", self.sut_restart)
        ltp.events.register("run_cmd_start", self.run_cmd_start)
        ltp.events.register("run_cmd_stdout", self.run_cmd_stdout)
        ltp.events.register("run_cmd_stop", self.run_cmd_stop)
        ltp.events.register("suite_download_started",
                            self.suite_download_started)
        ltp.events.register("suite_started", self.suite_started)
        ltp.events.register("suite_completed", self.suite_completed)
        ltp.events.register("session_error", self.session_error)
        ltp.events.register("internal_error", self.internal_error)

    def _print(self, msg: str, color: str = None, end: str = "\n"):
        """
        Print a message.
        """
        msg = msg.replace(self.RESET_SCREEN, '')
        msg = msg.replace('\r', '')

        if color and not self._no_colors:
            print(f"{color}{msg}{self.RESET_COLOR}", end=end, flush=True)
        else:
            print(msg, end=end, flush=True)

    @staticmethod
    def _user_friendly_duration(duration: float) -> str:
        """
        Return a user-friendly duration time from seconds.
        For example, "3670.234" becomes "1h 0m 10s".
        """
        minutes, seconds = divmod(duration, 60)
        hours, minutes = divmod(minutes, 60)
        uf_time = ""

        if hours > 0:
            uf_time = f"{hours:.0f}h {minutes:.0f}m {seconds:.0f}s"
        elif minutes > 0:
            uf_time = f"{minutes:.0f}m {seconds:.0f}s"
        else:
            uf_time = f"{seconds:.3f}s"

        return uf_time

    def _print_stdout(self, data: str) -> None:
        """
        Print stdout coming from command run or test.
        """
        if len(data) == 1:
            self._line += data
            if data == "\n":
                self._print(self._line, end='')
                self._line = ""
        else:
            lines = data.splitlines(True)
            if len(lines) > 0:
                for line in lines[:-1]:
                    self._line += line

                    self._print(self._line, end='')
                    self._line = ""

                self._line = lines[-1]

            if data.endswith('\n') and self._line:
                self._print(self._line, end='')
                self._line = ""

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

    def sut_start(self, sut: str) -> None:
        self._print(f"Connecting to SUT: {sut}")

    def sut_stop(self, sut: str) -> None:
        self._print(f"\nDisconnecting from SUT: {sut}")

    def sut_restart(self, sut: str) -> None:
        self._print(f"Restarting SUT: {sut}")

    def run_cmd_start(self, cmd: str) -> None:
        self._print(f"{cmd}", color=self.CYAN)

    def run_cmd_stdout(self, data: str) -> None:
        self._print_stdout(data)

    def run_cmd_stop(self, command: str, stdout: str, returncode: int) -> None:
        self._print(f"\nExit code: {returncode}\n")

    def suite_download_started(
            self,
            name: str,
            target: str) -> None:
        self._print(f"Downloading suite: {name}")

    def suite_started(self, suite: Suite) -> None:
        self._print(f"Starting suite: {suite.name}")

    def suite_completed(self, results: SuiteResults) -> None:
        duration = self._user_friendly_duration(results.exec_time)

        message = "\n"
        message += f"Suite Name: {results.suite.name}\n"
        message += f"Total Run: {len(results.suite.tests)}\n"
        message += f"Elapsed Time: {duration}\n"
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

    def suite_timeout(self, suite: Suite, timeout: float) -> None:
        self._print(
            f"Suite '{suite.name}' timed out after {timeout} seconds",
            color=self.RED)

    def session_error(self, error: str) -> None:
        self._print(f"Error: {error}", color=self.RED)

    def internal_error(self, exc: BaseException, func_name: str) -> None:
        self._print(
            f"\nUI error in function '{func_name}': {exc}\n",
            color=self.RED)


class SimpleUserInterface(ConsoleUserInterface):
    """
    Console based user interface without many fancy stuff.
    """

    def __init__(self, no_colors: bool = False) -> None:
        super().__init__(no_colors=no_colors)

        self._sut_not_responding = False
        self._kernel_panic = False
        self._kernel_tainted = None
        self._timed_out = False

        ltp.events.register("sut_not_responding", self.sut_not_responding)
        ltp.events.register("kernel_panic", self.kernel_panic)
        ltp.events.register("kernel_tainted", self.kernel_tainted)
        ltp.events.register("test_timed_out", self.test_timed_out)
        ltp.events.register("test_started", self.test_started)
        ltp.events.register("test_completed", self.test_completed)

    def sut_not_responding(self) -> None:
        self._sut_not_responding = True

    def kernel_panic(self) -> None:
        self._kernel_panic = True

    def kernel_tainted(self, message: str) -> None:
        self._kernel_tainted = message

    def test_timed_out(self, _: Test, timeout: int) -> None:
        self._timed_out = True

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

            if self._kernel_tainted:
                self._print(" | ", end="")
                self._print("tainted", color=self.YELLOW, end="")

            uf_time = self._user_friendly_duration(results.exec_time)
            self._print(f"  ({uf_time})")

        self._sut_not_responding = False
        self._kernel_panic = False
        self._kernel_tainted = None
        self._timed_out = False


class VerboseUserInterface(ConsoleUserInterface):
    """
    Verbose console based user interface.
    """

    def __init__(self, no_colors: bool = False) -> None:
        super().__init__(no_colors=no_colors)

        self._timed_out = False

        ltp.events.register("sut_stdout_line", self.sut_stdout_line)
        ltp.events.register("kernel_tainted", self.kernel_tainted)
        ltp.events.register("test_timed_out", self.test_timed_out)
        ltp.events.register("test_started", self.test_started)
        ltp.events.register("test_completed", self.test_completed)
        ltp.events.register("test_stdout_line", self.test_stdout_line)

    def sut_stdout_line(self, _: str, data: str) -> None:
        self._print_stdout(data)

    def kernel_tainted(self, message: str) -> None:
        self._print(f"Tained kernel: {message}", color=self.YELLOW)

    def test_timed_out(self, _: Test, timeout: int) -> None:
        self._timed_out = True

    def test_started(self, test: Test) -> None:
        self._print("\n===== ", end="")
        self._print(test.name, color=self.CYAN, end="")
        self._print(" =====")
        self._print("command: ", end="")
        self._print(f"{test.command} {' '.join(test.arguments)}")

    def test_completed(self, results: TestResults) -> None:
        if self._timed_out:
            self._print("Test timed out", color=self.RED)

        self._timed_out = False

        if "Summary:" not in results.stdout:
            self._print("\nSummary:")
            self._print(f"passed    {results.passed}")
            self._print(f"failed    {results.failed}")
            self._print(f"broken    {results.broken}")
            self._print(f"skipped   {results.skipped}")
            self._print(f"warnings  {results.warnings}")

        uf_time = self._user_friendly_duration(results.exec_time)
        self._print(f"\nDuration: {uf_time}\n")

    def test_stdout_line(self, _: Test, line: str) -> None:
        col = ""

        if "Kernel panic" in line:
            col = self.RED

        self._print(line, color=col)
