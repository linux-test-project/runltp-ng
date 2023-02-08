"""
.. module:: qemu
    :platform: Linux
    :synopsis: module containing the base for qemu SUT implementation

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import re
import time
import signal
import select
import string
import secrets
import logging
import threading
import subprocess
from ltp.sut import SUT
from ltp.sut import IOBuffer
from ltp.sut import SUTError
from ltp.sut import SUTTimeoutError
from ltp.sut import KernelPanicError
from ltp.utils import Timeout
from ltp.utils import LTPTimeoutError


class QemuBase(SUT):
    """
    This is a base class for qemu based SUT implementations.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger("ltp.qemu")
        self._comm_lock = threading.Lock()
        self._cmd_lock = threading.Lock()
        self._fetch_lock = threading.Lock()
        self._proc = None
        self._poller = None
        self._stop = False
        self._logged_in = False
        self._last_pos = 0
        self._last_read = ""

    def _get_command(self) -> str:
        """
        Return the full qemu command to execute.
        """
        raise NotImplementedError()

    def _login(self, timeout: float, iobuffer: IOBuffer) -> None:
        """
        Method that implements login after starting the qemu process.
        """
        raise NotImplementedError()

    def _get_transport(self) -> tuple:
        """
        Return a couple of transport_dev and transport_file used by
        qemu instance for transport configuration.
        """
        raise NotImplementedError()

    @staticmethod
    def _generate_string(length: int = 10) -> str:
        """
        Generate a random string of the given length.
        """
        out = ''.join(secrets.choice(string.ascii_letters + string.digits)
                      for _ in range(length))
        return out

    @property
    def is_running(self) -> bool:
        if self._proc is None:
            return False

        return self._proc.poll() is None

    def ping(self) -> float:
        if not self.is_running:
            raise SUTError("SUT is not running")

        _, _, exec_time = self._exec("test .", 1, None)

        return exec_time

    def _read_stdout(self, size: int, iobuffer: IOBuffer) -> str:
        """
        Read data from stdout.
        """
        if not self.is_running:
            return None

        data = os.read(self._proc.stdout.fileno(), size)
        rdata = data.decode(encoding="utf-8", errors="replace")
        rdata = rdata.replace('\r', '')

        # write on stdout buffers
        if iobuffer:
            iobuffer.write(rdata)

        return rdata

    def _write_stdin(self, data: str) -> None:
        """
        Write data on stdin.
        """
        if not self.is_running:
            return

        wdata = data.encode(encoding="utf-8")
        try:
            wbytes = os.write(self._proc.stdin.fileno(), wdata)
            if wbytes != len(wdata):
                raise SUTError("Can't write all data to stdin")
        except BrokenPipeError as err:
            if not self._stop:
                raise SUTError(err)

    def _wait_for(
            self,
            message: str,
            timeout: float,
            iobuffer: IOBuffer) -> str:
        """
        Wait a string from stdout.
        """
        if not self.is_running:
            return None

        stdout = self._last_read
        panic = False
        found = False

        with Timeout(timeout) as timer:
            while not found:
                events = self._poller.poll(0.1)

                # stop or panic when no events are available,
                # so we collect all stdout before exit
                if not events:
                    if self._stop:
                        break

                    if panic:
                        raise KernelPanicError()

                for fdesc, _ in events:
                    if fdesc != self._proc.stdout.fileno():
                        continue

                    data = self._read_stdout(1024, iobuffer)
                    if data:
                        stdout += data

                    # search for message inside stdout
                    message_pos = stdout.find(message)
                    if message_pos != -1:
                        self._last_read = stdout[message_pos + len(message):]
                        found = True
                        break

                    # turn on panic flag, so we rise it when all the
                    # stdout has been collected
                    if "Kernel panic" in stdout:
                        panic = True

                timer.check(
                    err_msg=f"Timed out waiting for {repr(message)}",
                    exc=SUTTimeoutError)

                if self._proc.poll() is not None:
                    break

        if panic:
            # if we ended before raising Kernel panic, we raise the exception
            raise KernelPanicError()

        return stdout

    def _exec(self, command: str, timeout: float, iobuffer: IOBuffer) -> set:
        """
        Execute a command and return set(stdout, retcode, exec_time).
        """
        self._logger.debug("Execute (timeout %f): %s", timeout, repr(command))

        code = self._generate_string()

        msg = f"echo $?-{code}\n"
        if command and command.rstrip():
            msg = f"{command};" + msg

        self._logger.info("Sending %s", repr(msg))

        t_start = time.time()

        self._write_stdin(f"{command}; echo $?-{code}\n")
        stdout = self._wait_for(code, timeout, iobuffer)

        exec_time = time.time() - t_start

        retcode = -1

        if not self._stop:
            if stdout and stdout.rstrip():
                match = re.search(f"(?P<retcode>\\d+)-{code}", stdout)
                if not match and not self._stop:
                    raise SUTError(
                        f"Can't read return code from reply {repr(stdout)}")

                # first character is '\n'
                stdout = stdout[1:match.start()]

                try:
                    retcode = int(match.group("retcode"))
                except TypeError:
                    pass

        self._logger.debug(
            "stdout=%s, retcode=%d, exec_time=%d",
            repr(stdout),
            retcode,
            exec_time)

        return stdout, retcode, exec_time

    # pylint: disable=too-many-branches
    # some pylint versions don't recognize threading::Lock::locked
    # pylint: disable=no-member
    def stop(
            self,
            timeout: float = 30,
            iobuffer: IOBuffer = None) -> None:
        if not self.is_running:
            return

        self._logger.info("Shutting down virtual machine")
        self._stop = True

        with Timeout(timeout) as timer:
            try:
                # stop command first
                if self._cmd_lock.locked() or self._fetch_lock.locked():
                    self._logger.info("Stop running command")

                    # send interrupt character (equivalent of CTRL+C)
                    self._write_stdin('\x03')

                # wait until command ends
                while self._cmd_lock.locked():
                    time.sleep(1e-6)
                    timer.check(err_msg="Timed out during stop")

                # wait until fetching file is ended
                while self._fetch_lock.locked():
                    time.sleep(1e-6)
                    timer.check(err_msg="Timed out during stop")

                # logged in -> poweroff
                if self._logged_in:
                    self._logger.info("Poweroff virtual machine")

                    self._write_stdin("poweroff\n")

                    while self.is_running:
                        events = self._poller.poll(1)
                        for fdesc, _ in events:
                            if fdesc != self._proc.stdout.fileno():
                                continue

                            self._read_stdout(1, iobuffer)

                        try:
                            timer.check()
                        except LTPTimeoutError:
                            # let process to be killed
                            pass

                # still running -> stop process
                if self.is_running:
                    self._logger.info("Killing virtual machine process")

                    self._proc.send_signal(signal.SIGHUP)

                # wait communicate() to end
                while self._comm_lock.locked():
                    time.sleep(1e-6)
                    timer.check(err_msg="Timed out during stop")

                # wait for process to end
                while self.is_running:
                    time.sleep(1e-6)
                    timer.check(err_msg="Timed out during stop")

            finally:
                self._stop = False

    def force_stop(
            self,
            timeout: float = 30,
            iobuffer: IOBuffer = None) -> None:
        if not self.is_running:
            return

        self._logger.info("Shutting down virtual machine")
        self._stop = True

        with Timeout(timeout) as timer:
            try:
                # still running -> stop process
                if self.is_running:
                    self._logger.info("Killing virtual machine process")

                    self._proc.send_signal(signal.SIGKILL)

                    # stop command first
                    while self._cmd_lock.locked():
                        time.sleep(1e-6)
                        timer.check(err_msg="Timed out during stop")

                    # wait communicate() to end
                    while self._comm_lock.locked():
                        time.sleep(1e-6)
                        timer.check(err_msg="Timed out during stop")

                    # wait for process to end
                    while self.is_running:
                        time.sleep(1e-6)
                        timer.check(err_msg="Timed out during stop")
            finally:
                self._stop = False

    def communicate(
            self,
            timeout: float = 3600,
            iobuffer: IOBuffer = None) -> None:
        if self.is_running:
            raise SUTError("Virtual machine is already running")

        error = None

        with self._comm_lock:
            self._logged_in = False

            cmd = self._get_command()

            self._logger.info("Starting virtual machine")
            self._logger.debug(cmd)

            # pylint: disable=consider-using-with
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stdin=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=True)

            self._poller = select.epoll()
            self._poller.register(
                self._proc.stdout.fileno(),
                select.POLLIN |
                select.POLLPRI |
                select.POLLHUP |
                select.POLLERR)

            try:
                self._login(timeout, iobuffer)
                self._logged_in = True
                self._logger.info("Logged inside virtual machine")
            except SUTError as err:
                error = err

        if not self._stop and error:
            if self.is_running:
                # this can happen when shell is available but
                # something happened during commands execution
                self.stop(iobuffer=iobuffer)

            raise SUTError(error)

    def run_command(
            self,
            command: str,
            timeout: float = 3600,
            iobuffer: IOBuffer = None) -> dict:
        if not command:
            raise ValueError("command is empty")

        if not self.is_running:
            raise SUTError("Virtual machine is not running")

        with self._cmd_lock:
            self._logger.info("Running command: %s", command)

            stdout, retcode, exec_time = self._exec(
                f"{command}",
                timeout,
                iobuffer)

            ret = {
                "command": command,
                "timeout": timeout,
                "returncode": retcode,
                "stdout": stdout,
                "exec_time": exec_time,
            }

            self._logger.debug(ret)

            return ret

    def fetch_file(
            self,
            target_path: str,
            timeout: float = 3600) -> bytes:
        if not target_path:
            raise ValueError("target path is empty")

        if not self.is_running:
            raise SUTError("Virtual machine is not running")

        with self._fetch_lock:
            self._logger.info("Downloading %s", target_path)

            _, retcode, _ = self._exec(f'test -f {target_path}', 1, None)
            if retcode != 0:
                raise SUTError(f"'{target_path}' doesn't exist")

            transport_dev, transport_path = self._get_transport()

            stdout, retcode, _ = self._exec(
                f"cat {target_path} > {transport_dev}",
                timeout,
                None)

            if self._stop:
                return bytes()

            if retcode not in [0, signal.SIGHUP, signal.SIGKILL]:
                raise SUTError(
                    f"Can't send file to {transport_dev}: {stdout}")

            # read back data and send it to the local file path
            file_size = os.path.getsize(transport_path)

            retdata = bytes()

            with Timeout(timeout) as timer:
                with open(transport_path, "rb") as transport:
                    while not self._stop and self._last_pos < file_size:
                        timer.check(
                            err_msg=f"Timed out during transfer "
                            f"{target_path} (timeout={timeout})",
                            exc=SUTTimeoutError)

                        transport.seek(self._last_pos)
                        data = transport.read(4096)

                        retdata += data

                        self._last_pos = transport.tell()

            self._logger.info("File downloaded")

            return retdata
