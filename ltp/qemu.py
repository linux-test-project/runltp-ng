"""
.. module:: qemu
    :platform: Linux
    :synopsis: module containing qemu SUT implementation

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import re
import time
import signal
import select
import string
import shutil
import secrets
import logging
import threading
import subprocess
import ltp.sut
from ltp.sut import SUT
from ltp.sut import IOBuffer
from ltp.sut import SUTError
from ltp.sut import SUTTimeoutError


# pylint: disable=too-many-instance-attributes
class QemuSUT(SUT):
    """
    Qemu SUT spawn a new VM using qemu and execute commands inside it.
    This SUT implementation can be used to run commands inside
    a protected, virtualized environment.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__()

        self._logger = logging.getLogger("ltp.qemu")
        self._tmpdir = kwargs.get("tmpdir", None)
        self._image = kwargs.get("image", None)
        self._image_overlay = kwargs.get("image_overlay", None)
        self._ro_image = kwargs.get("ro_image", None)
        self._password = kwargs.get("password", "root")
        self._opts = kwargs.get("options", None)
        self._ram = kwargs.get("ram", "2G")
        self._smp = kwargs.get("smp", "2")
        self._virtfs = kwargs.get("virtfs", None)
        self._serial_type = kwargs.get("serial", "isa")
        self._env = kwargs.get("env", None)
        self._cwd = kwargs.get("cwd", None)
        self._proc = None
        self._poller = None
        self._stop = False
        self._comm_lock = threading.Lock()
        self._cmd_lock = threading.Lock()
        self._fetch_lock = threading.Lock()
        self._ps1 = f"#{self._generate_string()}#"
        self._logged_in = False
        self._last_pos = 0

        system = kwargs.get("system", "x86_64")
        self._qemu_cmd = f"qemu-system-{system}"

        if not self._tmpdir or not os.path.isdir(self._tmpdir):
            raise ValueError(
                f"Temporary directory doesn't exist: {self._tmpdir}")

        if not self._image or not os.path.isfile(self._image):
            raise ValueError(
                f"Image location doesn't exist: {self._image}")

        if self._ro_image and not os.path.isfile(self._ro_image):
            raise ValueError(
                f"Read-only image location doesn't exist: {self._ro_image}")

        if not self._ram:
            raise ValueError("RAM is not defined")

        if not self._smp:
            raise ValueError("CPU is not defined")

        if self._virtfs and not os.path.isdir(self._virtfs):
            raise ValueError(
                f"Virtual FS directory doesn't exist: {self._virtfs}")

        if self._serial_type not in ["isa", "virtio"]:
            raise ValueError("Serial protocol must be isa or virtio")

    @staticmethod
    def _generate_string(length: int = 10) -> str:
        """
        Generate a random string of the given length.
        """
        out = ''.join(secrets.choice(string.ascii_letters + string.digits)
                      for _ in range(length))
        return out

    def _get_transport(self) -> str:
        """
        Return a couple of transport_dev and transport_file used by
        qemu instance for transport configuration.
        """
        pid = os.getpid()
        transport_file = os.path.join(self._tmpdir, f"transport-{pid}")
        transport_dev = ""

        if self._serial_type == "isa":
            transport_dev = "/dev/ttyS1"
        elif self._serial_type == "virtio":
            transport_dev = "/dev/vport1p1"

        return transport_dev, transport_file

    def _get_command(self) -> str:
        """
        Return the full qemu command to execute.
        """
        pid = os.getpid()
        tty_log = os.path.join(self._tmpdir, f"ttyS0-{pid}.log")

        image = self._image
        if self._image_overlay:
            shutil.copyfile(
                self._image,
                self._image_overlay)
            image = self._image_overlay

        params = []
        params.append("-enable-kvm")
        params.append("-display none")
        params.append(f"-m {self._ram}")
        params.append(f"-smp {self._smp}")
        params.append("-device virtio-rng-pci")
        params.append(f"-drive if=virtio,cache=unsafe,file={image}")
        params.append(f"-chardev stdio,id=tty,logfile={tty_log}")

        if self._serial_type == "isa":
            params.append("-serial chardev:tty")
            params.append("-serial chardev:transport")
        elif self._serial_type == "virtio":
            params.append("-device virtio-serial")
            params.append("-device virtconsole,chardev=tty")
            params.append("-device virtserialport,chardev=transport")
        else:
            raise NotImplementedError(
                f"Unsupported serial device type {self._serial_type}")

        _, transport_file = self._get_transport()
        params.append(f"-chardev file,id=transport,path={transport_file}")

        if self._ro_image:
            params.append(
                "-drive read-only,"
                "if=virtio,"
                "cache=unsafe,"
                f"file={self._ro_image}")

        if self._virtfs:
            params.append(
                "-virtfs local,"
                f"path={self._virtfs},"
                "mount_tag=host0,"
                "security_model=mapped-xattr,"
                "readonly=on")

        if self._opts:
            params.extend(self._opts)

        cmd = f"{self._qemu_cmd} {' '.join(params)}"

        return cmd

    @property
    def name(self) -> str:
        return "qemu"

    @property
    def is_running(self) -> bool:
        if self._proc is None:
            return False

        return self._proc.poll() is None

    def ping(self) -> float:
        if not self.is_running:
            raise SUTError("SUT is not running")

        ret = self.run_command("test .", timeout=1)
        reply_t = ret["exec_time"]

        return reply_t

    def get_info(self) -> dict:
        self._logger.info("Reading SUT information")

        ret = ltp.sut.collect_sysinfo(self)
        ret.pop("kernel_tained")

        self._logger.debug(ret)

        return ret

    def get_tained_info(self) -> set:
        self._logger.info("Checking for tained kernel")

        code, messages = ltp.sut.collect_sysinfo(self)["kernel_tained"]

        self._logger.debug("code=%d, messages=%s", code, messages)

        return code, messages

    def _read_stdout(self, size: int, iobuffer: IOBuffer) -> bytes:
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

        t_secs = max(timeout, 0)
        t_start = time.time()
        stdout = ""

        while not stdout.endswith(message):
            events = self._poller.poll(0.5)
            for fdesc, _ in events:
                if fdesc != self._proc.stdout.fileno():
                    continue

                data = self._read_stdout(1, iobuffer)
                if data:
                    stdout += data

            if time.time() - t_start >= t_secs:
                raise SUTTimeoutError(
                    f"Timed out waiting for {repr(message)}")

            if self._proc.poll() is not None:
                break

        return stdout

    def _exec(self, command: str, timeout: float, iobuffer: IOBuffer) -> str:
        """
        Execute a command and wait for command prompt.
        """
        self._logger.debug("Execute (timeout %f): %s", timeout, repr(command))

        self._write_stdin(command)
        self._wait_for(command, 5, iobuffer)  # ignore echo

        stdout = self._wait_for(self._ps1, timeout, iobuffer)

        # we don't want to keep prompt string at the end of the stdout
        if stdout and stdout.endswith(self._ps1):
            stdout = stdout[:-len(self._ps1)]

        return stdout

    # pylint: disable=too-many-branches
    def stop(
            self,
            timeout: float = 30,
            iobuffer: IOBuffer = None) -> None:
        if not self.is_running:
            return

        self._logger.info("Shutting down virtual machine")
        self._stop = True

        t_secs = max(timeout, 0)

        # some pylint versions don't recognize threading::Lock::locked
        # pylint: disable=no-member

        try:
            # stop command first
            if self._cmd_lock.locked():
                self._logger.info("Stop running command")

                # send interrupt character (equivalent of CTRL+C)
                self._write_stdin('\x03')

                start_t = time.time()
                while self._cmd_lock.locked():
                    time.sleep(0.05)
                    if time.time() - start_t >= t_secs:
                        raise SUTTimeoutError("Timed out during stop")

            # wait until fetching file is ended
            if self._fetch_lock.locked():
                self._logger.info("Stop fetching file")

                start_t = time.time()
                while self._fetch_lock.locked():
                    time.sleep(0.05)
                    if time.time() - start_t >= t_secs:
                        raise SUTTimeoutError("Timed out during stop")

            # logged in -> poweroff
            if self._logged_in:
                self._logger.info("Poweroff virtual machine")

                self._exec("\n", 5, iobuffer)
                self._write_stdin("poweroff\n")

                start_t = time.time()
                while self._proc.poll() is None:
                    events = self._poller.poll(1)
                    for fdesc, _ in events:
                        if fdesc != self._proc.stdout.fileno():
                            continue

                        self._read_stdout(1, iobuffer)

                    if time.time() - start_t >= t_secs:
                        break

            # still running -> stop process
            if self._proc.poll() is None:
                self._logger.info("Killing virtual machine process")

                self._proc.send_signal(signal.SIGHUP)

            # wait communicate() to end
            if self._comm_lock.locked():
                start_t = time.time()
                while self._comm_lock.locked():
                    time.sleep(0.05)
                    if time.time() - start_t >= t_secs:
                        raise SUTTimeoutError("Timed out during stop")

            # wait for process to end
            start_t = time.time()
            while self._proc.poll() is None:
                time.sleep(0.05)
                if time.time() - start_t >= t_secs:
                    raise SUTTimeoutError("Timed out during stop")
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

        t_secs = max(timeout, 0)

        try:
            # still running -> stop process
            if self._proc.poll() is None:
                self._logger.info("Killing virtual machine process")

                self._proc.send_signal(signal.SIGKILL)

                # wait for process to end
                start_t = time.time()
                while self._proc.poll() is None:
                    time.sleep(0.05)
                    if time.time() - start_t >= t_secs:
                        raise SUTTimeoutError("Timed out during stop")
        finally:
            self._stop = False

    def communicate(
            self,
            timeout: float = 3600,
            iobuffer: IOBuffer = None) -> None:
        if not shutil.which(self._qemu_cmd):
            raise SUTError(f"Command not found: {self._qemu_cmd}")

        if self.is_running:
            raise SUTError("Virtual machine is already running")

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
                self._wait_for("login:", timeout, iobuffer)
                self._write_stdin("root\n")
                self._wait_for("Password:", 5, iobuffer)
                self._write_stdin(f"{self._password}\n")
                self._wait_for("#", 5, iobuffer)

                ret = self.run_command(
                    f"export PS1={self._ps1}",
                    timeout=5,
                    iobuffer=iobuffer)
                if ret["returncode"] != 0:
                    raise SUTError("Can't setup prompt string")

                if self._cwd:
                    ret = self.run_command(
                        f"cd {self._cwd}",
                        timeout=5,
                        iobuffer=iobuffer)
                    if ret["returncode"] != 0:
                        raise SUTError("Can't setup current working directory")

                if self._env:
                    for key, value in self._env.items():
                        ret = self.run_command(
                            f"export {key}={value}",
                            timeout=5,
                            iobuffer=iobuffer)
                        if ret["returncode"] != 0:
                            raise SUTError(f"Can't setup env {key}={value}")

                self._logged_in = True

                if self._virtfs:
                    ret = self.run_command(
                        "mount -t 9p -o trans=virtio host0 /mnt",
                        timeout=10,
                        iobuffer=iobuffer)
                    if ret["returncode"] != 0:
                        raise SUTError("Failed to mount virtfs")

                self._logger.info("Virtual machine started")
            except SUTError as err:
                if not self._stop:
                    raise SUTError(err)

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

            code = self._generate_string()

            # send command
            t_start = time.time()
            stdout = self._exec(f"{command}\n", timeout, iobuffer)
            t_end = time.time() - t_start

            # read return code
            reply = self._exec(f"echo $?-{code}\n", 5, iobuffer)

            retcode = -1

            if reply:
                match = re.search(f"^(?P<retcode>\\d+)-{code}", reply)
                if not match:
                    raise SUTError(
                        f"Can't read return code from reply {repr(reply)}")

                try:
                    retcode = int(match.group("retcode"))
                except TypeError:
                    pass

            ret = {
                "command": command,
                "timeout": timeout,
                "returncode": retcode,
                "stdout": stdout,
                "exec_time": t_end,
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

            ret = self.run_command(f'test -f {target_path}', timeout=1)
            if ret["returncode"] != 0:
                raise SUTError(f"'{target_path}' doesn't exist")

            transport_dev, transport_path = self._get_transport()

            ret = self.run_command(
                f"cat {target_path} > {transport_dev}",
                timeout=timeout)

            retcode = ret["returncode"]
            stdout = ret["stdout"]

            if retcode not in [0, signal.SIGHUP, signal.SIGKILL]:
                raise SUTError(f"Can't send file to {transport_dev}: {stdout}")

            # read back data and send it to the local file path
            file_size = os.path.getsize(transport_path)
            start_t = time.time()

            retdata = bytes()

            with open(transport_path, "rb") as transport:
                while not self._stop and self._last_pos < file_size:
                    if time.time() - start_t >= timeout:
                        self._logger.info(
                            "Transfer timed out after %d seconds",
                            timeout)

                        raise SUTTimeoutError(
                            f"Timed out during transfer {target_path}"
                            f"(timeout={timeout})")

                    time.sleep(0.05)

                    transport.seek(self._last_pos)
                    data = transport.read(4096)

                    retdata += data

                    self._last_pos = transport.tell()

            self._logger.info("File downloaded")

            return retdata
