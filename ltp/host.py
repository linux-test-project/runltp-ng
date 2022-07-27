"""
.. module:: host
    :platform: Linux
    :synopsis: module containing host SUT implementation

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import time
import select
import signal
import logging
import threading
import subprocess
from .sut import SUT, IOBuffer
from .sut import SUTError
from .sut import SUTTimeoutError


class HostSUT(SUT):
    """
    SUT implementation using host's shell.
    """

    def __init__(self, cwd: str = None, env: dict = None) -> None:
        super().__init__()

        self._logger = logging.getLogger("ltp.host")
        self._proc = None
        self._stop = False
        self._initialized = False
        self._cwd = cwd
        self._env = env
        self._cmd_lock = threading.Lock()
        self._fetch_lock = threading.Lock()

    @property
    def name(self) -> str:
        return "host"

    @property
    def is_running(self) -> bool:
        return self._initialized

    def ping(self) -> float:
        if not self.is_running:
            raise SUTError("SUT is not running")

        ret = self.run_command("test .", timeout=1)
        reply_t = ret["exec_time"]

        return reply_t

    def get_info(self) -> dict:
        self._logger.info("Reading SUT information")

        # create suite results
        def _run_cmd(cmd: str) -> str:
            """
            Run command, check for returncode and return command's stdout.
            """
            ret = self.run_command(cmd, timeout=3)
            if ret["returncode"] != 0:
                raise SUTError(f"Can't read information from SUT: {cmd}")

            stdout = ret["stdout"].rstrip()

            return stdout

        distro = _run_cmd(". /etc/os-release; echo \"$ID\"")
        distro_ver = _run_cmd(". /etc/os-release; echo \"$VERSION_ID\"")
        kernel = _run_cmd("uname -s -r -v")
        arch = _run_cmd("uname -m")

        ret = {
            "distro": distro,
            "distro_ver": distro_ver,
            "kernel": kernel,
            "arch": arch,
        }

        self._logger.debug(ret)

        return ret

    def get_tained_info(self) -> set:
        self._logger.info("Checking for tained kernel")

        ret = self.run_command(
            "cat /proc/sys/kernel/tainted",
            timeout=1)

        if ret["returncode"]:
            raise SUTError("Can't check for tained kernel")

        tained_num = len(self.TAINED_MSG)
        code = int(ret["stdout"].rstrip())
        bits = format(code, f"0{tained_num}b")[::-1]

        messages = []
        for i in range(0, tained_num):
            if bits[i] == "1":
                msg = self.TAINED_MSG[i]
                messages.append(msg)

        self._logger.debug("code=%d, messages=%s", code, messages)

        return code, messages

    def communicate(self,
                    timeout: float = 3600,
                    iobuffer: IOBuffer = None) -> None:
        if self.is_running:
            raise SUTError("SUT is running")

        self._initialized = True

    # some pylint versions don't recognize threading.Lock.locked()
    # pylint: disable=no-member
    def _inner_stop(self, sig: int, timeout: float = 30) -> None:
        """
        Wait process to stop.
        """
        if not self.is_running:
            return

        self._stop = True

        if self._proc:
            self._logger.info("Terminating process with %s", sig)
            self._proc.send_signal(sig)

        t_secs = max(timeout, 0)

        t_start = time.time()
        while self._fetch_lock.locked():
            time.sleep(0.05)
            if time.time() - t_start >= t_secs:
                raise SUTTimeoutError(
                    "Timeout waiting for command to stop")

        t_start = time.time()
        while self._cmd_lock.locked():
            time.sleep(0.05)
            if time.time() - t_start >= t_secs:
                raise SUTTimeoutError(
                    "Timeout waiting for command to stop")

        self._logger.info("Process terminated")

        self._initialized = False

    def stop(
        self,
        timeout: float = 30,
        iobuffer: IOBuffer = None) -> None:
        self._inner_stop(signal.SIGHUP, timeout)

    def force_stop(
        self,
        timeout: float = 30,
        iobuffer: IOBuffer = None) -> None:
        self._inner_stop(signal.SIGKILL, timeout)

    def _read_stdout(self, size: int, iobuffer: IOBuffer = None) -> bytes:
        """
        Read data from stdout.
        """
        if not self.is_running:
            return None

        data = os.read(self._proc.stdout.fileno(), size)

        # write on stdout buffers
        if iobuffer:
            iobuffer.write(data)
            iobuffer.flush()

        rdata = data.decode(encoding="utf-8", errors="replace")
        rdata = rdata.replace('\r', '')

        return rdata

    # pylint: disable=too-many-locals
    def run_command(self,
                    command: str,
                    timeout: float = 3600,
                    iobuffer: IOBuffer = None) -> dict:
        if not command:
            raise ValueError("command is empty")

        if not self.is_running:
            raise SUTError("SUT is not running")

        with self._cmd_lock:
            t_secs = max(timeout, 0)

            self._logger.info("Executing command (timeout=%d): %s",
                t_secs,
                command)

            # pylint: disable=consider-using-with
            self._proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=self._cwd,
                env=self._env,
                shell=True)

            ret = None
            t_start = time.time()
            t_end = 0
            stdout = ""

            try:
                poller = select.epoll()
                poller.register(
                    self._proc.stdout.fileno(),
                    select.POLLIN |
                    select.POLLPRI |
                    select.POLLHUP |
                    select.POLLERR)

                while True:
                    events = poller.poll(1)
                    for fdesc, _ in events:
                        if fdesc != self._proc.stdout.fileno():
                            break

                        data = self._read_stdout(1024, iobuffer)
                        if data:
                            stdout += data

                    if self._proc.poll() is not None:
                        break

                    if time.time() - t_start >= t_secs:
                        raise SUTTimeoutError(
                            "Timeout during command execution")

                t_end = time.time() - t_start
            except subprocess.TimeoutExpired as err:
                self._proc.kill()
                raise SUTError(err)
            finally:
                ret = {
                    "command": command,
                    "stdout": stdout,
                    "returncode": self._proc.returncode,
                    "timeout": t_secs,
                    "exec_time": t_end,
                }

                self._logger.debug("return data=%s", ret)
                self._proc = None

            self._logger.info("Command executed")

            return ret

    def fetch_file(
            self,
            target_path: str,
            timeout: float = 3600) -> bytes:
        if not target_path:
            raise ValueError("target path is empty")

        if not os.path.isfile(target_path):
            raise SUTError(f"'{target_path}' file doesn't exist")

        with self._fetch_lock:
            self._logger.info("Downloading '%s'", target_path)
            self._stop = False

            retdata = bytes()

            try:
                start_t = time.time()

                with open(target_path, 'rb') as ftarget:
                    data = ftarget.read(1024)

                    while data != b'' and not self._stop:
                        retdata += data
                        data = ftarget.read(1024)

                        if time.time() - start_t >= timeout:
                            self._logger.info(
                                "Transfer timed out after %d seconds",
                                timeout)

                            raise SUTTimeoutError(
                                f"Timeout when transfer {target_path}"
                                f" (timeout={timeout}):")
            except IOError as err:
                raise SUTError(err)
            finally:
                if self._stop:
                    self._logger.info("Copy stopped")
                else:
                    self._logger.info("File copied")

            return retdata
