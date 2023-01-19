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
from ltp.sut import SUT
from ltp.sut import IOBuffer
from ltp.sut import SUTError
from ltp.sut import SUTTimeoutError
from ltp.sut import KernelPanicError
from ltp.utils import Timeout
from ltp.utils import LTPTimeoutError


# pylint: disable=too-many-instance-attributes
class QemuSUT(SUT):
    """
    Qemu SUT spawn a new VM using qemu and execute commands inside it.
    This SUT implementation can be used to run commands inside
    a protected, virtualized environment.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger("ltp.qemu")
        self._comm_lock = threading.Lock()
        self._cmd_lock = threading.Lock()
        self._fetch_lock = threading.Lock()
        self._tmpdir = None
        self._env = None
        self._cwd = None
        self._proc = None
        self._poller = None
        self._stop = False
        self._logged_in = False
        self._last_pos = 0
        self._image = None
        self._image_overlay = None
        self._ro_image = None
        self._password = None
        self._ram = None
        self._smp = None
        self._virtfs = None
        self._serial_type = None
        self._qemu_cmd = None
        self._opts = None

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
            params.append(self._opts)

        cmd = f"{self._qemu_cmd} {' '.join(params)}"

        return cmd

    def setup(self, **kwargs: dict) -> None:
        self._logger.info("Initialize SUT")

        self._env = kwargs.get("env", None)
        self._cwd = kwargs.get("cwd", None)
        self._tmpdir = kwargs.get("tmpdir", None)
        self._image = kwargs.get("image", None)
        self._image_overlay = kwargs.get("image_overlay", None)
        self._ro_image = kwargs.get("ro_image", None)
        self._password = kwargs.get("password", "root")
        self._ram = kwargs.get("ram", "2G")
        self._smp = kwargs.get("smp", "2")
        self._virtfs = kwargs.get("virtfs", None)
        self._serial_type = kwargs.get("serial", "isa")
        self._opts = kwargs.get("options", None)

        system = kwargs.get("system", "x86_64")
        self._qemu_cmd = f"qemu-system-{system}"

        if not self._tmpdir or not os.path.isdir(self._tmpdir):
            raise SUTError(
                f"Temporary directory doesn't exist: {self._tmpdir}")

        if not self._image or not os.path.isfile(self._image):
            raise SUTError(
                f"Image location doesn't exist: {self._image}")

        if self._ro_image and not os.path.isfile(self._ro_image):
            raise SUTError(
                f"Read-only image location doesn't exist: {self._ro_image}")

        if not self._ram:
            raise SUTError("RAM is not defined")

        if not self._smp:
            raise SUTError("CPU is not defined")

        if self._virtfs and not os.path.isdir(self._virtfs):
            raise SUTError(
                f"Virtual FS directory doesn't exist: {self._virtfs}")

        if self._serial_type not in ["isa", "virtio"]:
            raise SUTError("Serial protocol must be isa or virtio")

    @property
    def config_help(self) -> dict:
        return dict(
            image="qcow2 image location",
            image_overlay="image_overlay: image copy location",
            password="root password (default: root)",
            system="system architecture (default: x86_64)",
            ram="RAM of the VM (default: 2G)",
            smp="number of CPUs (default: 2)",
            serial="type of serial protocol. isa|virtio (default: isa)",
            virtfs="directory to mount inside VM",
            ro_image="path of the image that will exposed as read only",
            options="user defined options",
        )

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
            iobuffer.flush()

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

        stdout = ""
        panic = False

        with Timeout(timeout) as timer:
            while not stdout.endswith(message):
                events = self._poller.poll(0.1)

                if not events and self._stop:
                    break

                if not events and panic:
                    raise KernelPanicError()

                for fdesc, _ in events:
                    if fdesc != self._proc.stdout.fileno():
                        continue

                    data = self._read_stdout(1, iobuffer)
                    if data:
                        stdout += data

                    if stdout.endswith("Kernel panic"):
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
        if not shutil.which(self._qemu_cmd):
            raise SUTError(f"Command not found: {self._qemu_cmd}")

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
                self._wait_for("login:", timeout, iobuffer)
                self._write_stdin("root\n")

                if self._password:
                    self._wait_for("Password:", 5, iobuffer)
                    self._write_stdin(f"{self._password}\n")

                time.sleep(0.2)

                self._wait_for("#", 5, iobuffer)
                time.sleep(0.2)

                self._write_stdin("stty -echo; stty cols 1024\n")
                self._wait_for("#", 5, None)

                _, retcode, _ = self._exec("export PS1=''", 5, None)
                if retcode != 0:
                    raise SUTError("Can't setup prompt string")

                if self._virtfs:
                    _, retcode, _ = self._exec(
                        "mount -t 9p -o trans=virtio host0 /mnt",
                        10, None)
                    if retcode != 0:
                        raise SUTError("Failed to mount virtfs")

                if self._cwd:
                    _, retcode, _ = self._exec(f"cd {self._cwd}", 5, None)
                    if retcode != 0:
                        raise SUTError("Can't setup current working directory")

                if self._env:
                    for key, value in self._env.items():
                        _, retcode, _ = self._exec(
                            f"export {key}={value}",
                            5, None)
                        if retcode != 0:
                            raise SUTError(f"Can't setup env {key}={value}")

                self._logged_in = True

                self._logger.info("Virtual machine started")
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
