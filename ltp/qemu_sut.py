"""
.. module:: qemu_sut
    :platform: Linux
    :synopsis: module containing qemu SUT implementation

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import time
import shutil
from ltp.sut import SUTError
from ltp.sut import IOBuffer
from ltp.qemu import QemuBase


# pylint: disable=too-many-instance-attributes
class QemuSUT(QemuBase):
    """
    Qemu SUT implementation. It spawns a qemu instance and it runs commands
    inside, as well as trasfer files.
    """

    def __init__(self) -> None:
        super().__init__()
        self._qemu_cmd = None
        self._tmpdir = None
        self._env = None
        self._cwd = None
        self._image = None
        self._image_overlay = None
        self._ro_image = None
        self._password = None
        self._ram = None
        self._smp = None
        self._virtfs = None
        self._serial_type = None
        self._opts = None
        self._user = None
        self._prompt = None

    @property
    def name(self) -> str:
        return "qemu"

    @property
    def config_help(self) -> dict:
        return {
            "image": "qcow2 image location",
            "image_overlay": "image_overlay: image copy location",
            "user": "username used to login. If empty, it won't be used (default: 'root')",
            "password": "root password (default: root)",
            "system": "system architecture (default: x86_64)",
            "ram": "RAM of the VM (default: 2G)",
            "smp": "number of CPUs (default: 2)",
            "serial": "type of serial protocol. isa|virtio (default: isa)",
            "virtfs": "directory to mount inside VM",
            "ro_image": "path of the image that will exposed as read only",
            "options": "user defined options",
            "first_prompt": "first shell prompt string (default: '#')",
        }

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
            raise SUTError(
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

    def _login(self, timeout: float, iobuffer: IOBuffer) -> None:
        if self._user:
            self._wait_for("login:", timeout, iobuffer)
            self._write_stdin(f"{self._user}\n")

        if self._password:
            self._wait_for("Password:", 5, iobuffer)
            self._write_stdin(f"{self._password}\n")

        time.sleep(0.2)

        self._wait_for(self._prompt, timeout, iobuffer)
        time.sleep(0.2)

        self._write_stdin("stty -echo; stty cols 1024\n")
        self._wait_for(self._prompt, 5, None)

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

    def setup(self, **kwargs: dict) -> None:
        self._logger.info("Initialize SUT")

        self._env = kwargs.get("env", None)
        self._cwd = kwargs.get("cwd", None)
        self._tmpdir = kwargs.get("tmpdir", None)
        self._image = kwargs.get("image", None)
        self._image_overlay = kwargs.get("image_overlay", None)
        self._ro_image = kwargs.get("ro_image", None)
        self._user = kwargs.get("user", "root")
        self._password = kwargs.get("password", "root")
        self._ram = kwargs.get("ram", "2G")
        self._smp = kwargs.get("smp", "2")
        self._virtfs = kwargs.get("virtfs", None)
        self._serial_type = kwargs.get("serial", "isa")
        self._opts = kwargs.get("options", None)
        self._prompt = kwargs.get("first_prompt", "#")

        system = kwargs.get("system", "x86_64")
        self._qemu_cmd = f"qemu-system-{system}"

        if not shutil.which(self._qemu_cmd):
            raise SUTError(f"Command not found: {self._qemu_cmd}")

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

        if not self._prompt:
            raise SUTError("first_prompt is not defined")
