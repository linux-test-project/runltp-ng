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
from ltp.sut import SUT
from ltp.sut import IOBuffer
from ltp.sut import SUTError
from ltp.sut import SUTTimeoutError
from ltp.utils import Timeout


class HostSUT(SUT):
    """
    SUT implementation using host's shell.
    """

    # hack: this parameter is useful during unit testing, since we can
    # override it without using PropertyMock that seems to be bugged
    NAME = "host"

    def __init__(self) -> None:
        self._logger = logging.getLogger("ltp.host")
        self._initialized = False
        self._cmd_lock = threading.Lock()
        self._fetch_lock = threading.Lock()
        self._procs = []
        self._stop = False
        self._cwd = None
        self._env = None

    def setup(self, **kwargs: dict) -> None:
        self._logger.info("Initialize SUT")

        self._cwd = kwargs.get('cwd', None)
        self._env = kwargs.get('env', None)

    @property
    def config_help(self) -> dict:
        # cwd and env are given by default, so no options are needed
        return {}

    @property
    def name(self) -> str:
        return self.NAME

    @property
    def is_running(self) -> bool:
        return self._initialized

    def ping(self) -> float:
        if not self.is_running:
            raise SUTError("SUT is not running")

        ret = self.run_command("test .", timeout=1)
        reply_t = ret["exec_time"]

        return reply_t

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

        with Timeout(timeout) as timer:
            if self._procs:
                self._logger.info(
                    "Terminating %d process(es) with %s",
                    len(self._procs), sig)

                for proc in self._procs:
                    proc.send_signal(sig)

                    while proc.poll() is None:
                        time.sleep(1e-6)
                        timer.check(
                            err_msg="Timeout waiting for command to stop")

            while self._fetch_lock.locked():
                time.sleep(1e-6)
                timer.check(err_msg="Timeout waiting to fetch file")

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

    def _read_stdout(
            self,
            proc: subprocess.Popen,
            size: int,
            iobuffer: IOBuffer = None) -> str:
        """
        Read data from stdout.
        """
        if not self.is_running:
            return None

        data = os.read(proc.stdout.fileno(), size)
        rdata = data.decode(encoding="utf-8", errors="replace")
        rdata = rdata.replace('\r', '')

        # write on stdout buffers
        if iobuffer:
            iobuffer.write(rdata)
            iobuffer.flush()

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

        t_secs = max(timeout, 0)

        self._logger.info(
            "Executing command (timeout=%.3f): %s",
            t_secs,
            command)

        # pylint: disable=consider-using-with
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=self._cwd,
            env=self._env,
            shell=True)

        self._procs.append(proc)

        ret = None
        t_start = time.time()
        t_end = 0
        stdout = ""

        try:
            poller = select.epoll()
            poller.register(
                proc.stdout.fileno(),
                select.POLLIN |
                select.POLLPRI |
                select.POLLHUP |
                select.POLLERR)

            with Timeout(timeout) as timer:
                while True:
                    events = poller.poll(0.1)
                    for fdesc, _ in events:
                        if fdesc != proc.stdout.fileno():
                            break

                        data = self._read_stdout(proc, 1024, iobuffer)
                        if data:
                            stdout += data

                    if proc.poll() is not None:
                        break

                    timer.check(
                        err_msg="Timeout during command execution",
                        exc=SUTTimeoutError)

            t_end = time.time() - t_start

            # once the process stopped, we still might have some data
            # inside the stdout buffer
            while not self._stop:
                data = self._read_stdout(proc, 1024, iobuffer)
                if not data:
                    break

                stdout += data
        finally:
            self._procs.remove(proc)

            ret = {
                "command": command,
                "stdout": stdout,
                "returncode": proc.returncode,
                "timeout": t_secs,
                "exec_time": t_end,
            }

            self._logger.debug("return data=%s", ret)

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
                with Timeout(timeout) as timer:
                    with open(target_path, 'rb') as ftarget:
                        data = ftarget.read(1024)

                        while data != b'' and not self._stop:
                            retdata += data
                            data = ftarget.read(1024)

                            timer.check(
                                err_msg=f"Timeout when transfer {target_path}"
                                f" (timeout={timeout})",
                                exc=SUTTimeoutError)
            except IOError as err:
                raise SUTError(err)
            finally:
                if self._stop:
                    self._logger.info("Copy stopped")
                else:
                    self._logger.info("File copied")

            return retdata
