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
from typing import IO
from .sut import SUT
from .sut import SUTError
from .sut import SUTTimeoutError


class HostSUT(SUT):
    """
    SUT implementation using host's shell.
    """

    def __init__(
            self,
            cwd: str = None,
            env: dict = None,
            iobuffer: IO = None) -> None:
        self._logger = logging.getLogger("ltp.host")
        self._proc = None
        self._stop = False
        self._initialized = False
        self._cwd = cwd
        self._env = env
        self._iobuffer = iobuffer
        self._cmd_lock = threading.Lock()

    @property
    def name(self) -> str:
        return "host"

    @property
    def is_running(self) -> bool:
        return self._initialized

    def communicate(self) -> None:
        if self.is_running:
            raise SUTError("SUT is running")

        self._initialized = True

    def _wait_for_stop(self, timeout: float = 30) -> None:
        """
        Wait process to stop.
        """
        t_start = time.time()
        t_secs = max(timeout, 0)

        while self._cmd_lock.locked():
            if time.time() - t_start >= t_secs:
                raise SUTTimeoutError("Timeout waiting for command to stop")

    def stop(self, timeout: int = 30) -> None:
        if not self.is_running:
            return

        self._stop = True

        if self._proc:
            self._logger.info("Terminating process")
            self._proc.send_signal(signal.SIGHUP)
            self._logger.info("Process terminated")

        self._wait_for_stop(timeout=timeout)

        self._initialized = False

    def force_stop(self, timeout: int = 30) -> None:
        if not self.is_running:
            return

        self._stop = True

        if self._proc:
            self._logger.info("Killing process")
            self._proc.kill()
            self._logger.info("Process killed")

        self._wait_for_stop(timeout=timeout)

        self._initialized = False

    def _read_stdout(self, size: int) -> bytes:
        """
        Read data from stdout.
        """
        if not self.is_running:
            return None

        data = os.read(self._proc.stdout.fileno(), size)

        if self._iobuffer:
            self._iobuffer.write(data)
            self._iobuffer.flush()

        rdata = data.decode(encoding="utf-8", errors="ignore")
        rdata = rdata.replace('\r', '')

        return rdata

    def run_command(self, command: str, timeout: float = 3600) -> dict:
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
                    events = poller.poll()
                    for fd, _ in events:
                        if fd != self._proc.stdout.fileno():
                            break

                        data = self._read_stdout(1024)
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
            local_path: str,
            timeout: int = 3600) -> None:
        if not target_path:
            raise ValueError("target path is empty")

        if not local_path:
            raise ValueError("local path is empty")

        if not os.path.isfile(target_path):
            raise ValueError("target file doesn't exist")

        self._logger.info("Copy '%s' to '%s'", target_path, local_path)

        self._stop = False

        try:
            start_t = time.time()

            with open(target_path, 'rb') as ftarget:
                with open(local_path, 'wb+') as flocal:
                    data = ftarget.read(1024)

                    while data != b'' and not self._stop:
                        flocal.write(data)
                        data = ftarget.read(1024)

                        if time.time() - start_t >= timeout:
                            self._logger.info(
                                "Transfer timed out after %d seconds", timeout)

                            raise SUTTimeoutError(
                                f"Timeout during transfer (timeout={timeout}):"
                                f" {target_path} -> {local_path}")
        except IOError as err:
            raise SUTError(err)
        finally:
            if self._stop:
                self._logger.info("Copy stopped")
            else:
                self._logger.info("File copied")
