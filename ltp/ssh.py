"""
.. module:: ssh
    :platform: Linux
    :synopsis: module defining SSH SUT

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import re
import time
import select
import socket
import string
import secrets
import logging
import threading
import subprocess
import ltp.sut
from ltp.sut import SUT
from ltp.sut import IOBuffer
from ltp.sut import SUTError
from ltp.sut import SUTTimeoutError
from ltp.sut import KernelPanicError

try:
    from paramiko import SSHClient
    from paramiko import RejectPolicy
    from paramiko import AutoAddPolicy
    from paramiko import MissingHostKeyPolicy
    from paramiko import SSHException
    from paramiko import RSAKey
    from scp import SCPClient
    from scp import SCPException
except ModuleNotFoundError:
    pass

# pylint: disable=too-many-instance-attributes


class SSHSUT(SUT):
    """
    A SUT that is using SSH protocol con communicate and transfer data.
    """

    # pylint: disable=too-many-statements
    def __init__(self, **kwargs) -> None:
        """
        :param tmpdir: temporary directory
        :type tmpdir: str
        :param host: TCP address
        :type host: str
        :param port: TCP port
        :type port: int
        :param user: username for logging in
        :type user: str
        :param password: password for logging in
        :type password: str
        :param key_file: file of the SSH keys
        :type key_file: str
        :param known_hosts: known_hosts file location.
            Default: ~/.ssh/known_hosts
        :type known_hosts: str
        :param hostkey_policy: host key policy (auto, missing, reject).
            Default: auto
        :type hostkey_policy: str
        :param reset_cmd: reset command to execute during stop
        :type reset_cmd: str
        :param sudo: if 1, use sudo to access a root shell
        :type sudo: int
        :param env: environment variables
        :type env: dict
        :param cwd: current working directory
        :type cwd: dict
        """
        self._logger = logging.getLogger("ltp.sut.ssh")
        self._tmpdir = kwargs.get("tmpdir", None)
        self._host = kwargs.get("host", "localhost")
        self._port = int(kwargs.get("port", "22"))
        self._user = kwargs.get("user", "root")
        self._password = kwargs.get("password", None)
        key_file = kwargs.get("key_file", None)
        hostkey_policy = kwargs.get("hostkey_policy", "auto")
        known_hosts = kwargs.get("known_hosts", None)
        self._pkey = None
        self._reset_cmd = kwargs.get("reset_cmd", None)
        self._sudo = int(kwargs.get("sudo", 0)) == 1
        self._env = kwargs.get("env", None)
        self._cwd = kwargs.get("cwd", None)
        self._ps1 = f"#{self._generate_string()}#"
        self._cmd_lock = threading.Lock()
        self._comm_lock = threading.Lock()
        self._fetch_lock = threading.Lock()
        self._stop = False
        self._shell = None
        self._client = None
        self._no_paramiko = False

        if hostkey_policy not in ["auto", "missing", "reject"]:
            raise ValueError(f"'{hostkey_policy}' policy is not available")

        try:
            self._client = SSHClient()

            # if /dev/null is given, we emulate -o UserKnownHostsFile=/dev/null
            # avoiding know_hosts file usage
            self._logger.info("Loading system host keys: %s", known_hosts)
            if known_hosts != "/dev/null":
                self._client.load_system_host_keys(known_hosts)

            if hostkey_policy == "auto":
                self._logger.info("Using auto add policy for host keys")
                self._client.set_missing_host_key_policy(
                    AutoAddPolicy())
            elif hostkey_policy == "missing":
                self._logger.info("Using missing policy for host keys")
                self._client.set_missing_host_key_policy(
                    MissingHostKeyPolicy())
            else:
                self._logger.info("Using reject policy for host keys")
                # for security reasons, we choose "reject" as default behavior
                self._client.set_missing_host_key_policy(
                    RejectPolicy())
        except NameError:
            self._logger.info("Paramiko is not installed")
            self._no_paramiko = True

        if not self._tmpdir or not os.path.isdir(self._tmpdir):
            raise ValueError(
                f"Temporary directory doesn't exist: {self._tmpdir}")

        if not self._host:
            raise ValueError("host is empty")

        if not self._user:
            raise ValueError("user is empty")

        if self._port <= 0 or self._port >= 65536:
            raise ValueError("port is out of range")

        if key_file and not os.path.isfile(key_file):
            raise ValueError("private key doesn't exist")

        if key_file:
            self._logger.info("Reading key file: %s", key_file)
            self._pkey = RSAKey.from_private_key_file(key_file)

    @staticmethod
    def _generate_string(length: int = 10) -> str:
        """
        Generate a random string of the given length.
        """
        out = ''.join(secrets.choice(string.ascii_letters + string.digits)
                      for _ in range(length))
        return out

    # pylint: disable=too-many-locals
    def _exec(self, command: str, timeout: float, iobuffer: IOBuffer) -> str:
        """
        Execute a command and wait for command prompt.
        """
        if not self.is_running:
            return None

        self._logger.debug("Execute (timeout %f): %s", timeout, repr(command))

        try:
            self._shell.send(command.encode(encoding="utf-8", errors="ignore"))
        except BrokenPipeError as err:
            if not self._stop:
                raise SUTError(err)

        stdout = ""
        t_secs = max(timeout, 0)
        t_start = time.time()
        panic = False

        # register stdout poller
        stdout_fd = self._shell.fileno()
        poller = select.epoll()
        poller.register(
            stdout_fd,
            select.POLLIN |
            select.POLLPRI |
            select.POLLHUP |
            select.POLLERR)

        while not stdout.endswith(self._ps1):
            if self._shell is None:
                # this can happen during stop()
                break

            events = poller.poll(1)

            if not events and panic:
                raise KernelPanicError()

            for fdesc, _ in events:
                if fdesc != stdout_fd:
                    break

                if self._shell is not None and self._shell.recv_ready():
                    data = self._shell.recv(512)
                    sdata = data.decode(encoding="utf-8", errors="ignore")
                    stdout += sdata.replace("\r", "")

                    # write on stdout buffers
                    if iobuffer:
                        iobuffer.write(data)
                        iobuffer.flush()

                    if stdout.endswith("Kernel panic"):
                        panic = True

                    if time.time() - t_start >= t_secs:
                        raise SUTTimeoutError(
                            f"Timed out waiting for {repr(self._ps1)}")

        # we don't want echo message
        if stdout and stdout.startswith(command):
            stdout = stdout[len(command):]

        # we don't want prompt string at the end of the stdout
        if stdout and "PS1" not in stdout and stdout.endswith(self._ps1):
            stdout = stdout[:-len(self._ps1)]

        return stdout

    @property
    def name(self) -> str:
        return "ssh"

    @property
    def is_running(self) -> bool:
        if self._no_paramiko:
            raise SUTError("Paramiko is not present on system")

        if self._client and self._client.get_transport():
            return self._client.get_transport().is_active()

        return False

    def ping(self) -> float:
        if not self.is_running:
            raise SUTError("SSH connection is not present")

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

    def communicate(
            self,
            timeout: float = 3600,
            iobuffer: IOBuffer = None) -> None:
        if self.is_running:
            raise SUTError("SSH connection is already present")

        with self._comm_lock:
            try:
                self._logger.info(
                    "Connecting to %s:%d",
                    self._host,
                    self._port)

                self._client.connect(
                    self._host,
                    port=self._port,
                    username=self._user,
                    password=self._password,
                    pkey=self._pkey,
                    timeout=timeout)

                self._logger.info("Initialize shell")

                self._shell = self._client.invoke_shell()

                # hack: wait for prompt. We don't know what the welcome
                # message will be, so we blindly wait for an amount of time
                # before proceeding with commands
                time.sleep(1)

                if self._sudo:
                    self._logger.info("Login with root")
                    self._shell.send("sudo /bin/sh\n".encode(encoding="utf-8"))
                    time.sleep(0.2)

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

                self._logger.info("Connected to host")
            except SSHException as err:
                raise SUTError(err)
            except socket.error as err:
                raise SUTError(err)
            except ValueError as err:
                raise SUTError(err)

    def _reset(self, timeout: float = 30, iobuffer: IOBuffer = None) -> None:
        """
        Run the reset command on host.
        """
        if not self._reset_cmd:
            return

        self._logger.info("Executing reset command: %s", repr(self._reset_cmd))

        with subprocess.Popen(
                self._reset_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=True) as proc:
            stdout = proc.stdout.fileno()
            poller = select.epoll()
            poller.register(
                stdout,
                select.POLLIN |
                select.POLLPRI |
                select.POLLHUP |
                select.POLLERR)

            t_secs = max(timeout, 0)
            t_start = time.time()

            while True:
                events = poller.poll(0.2)
                for fdesc, _ in events:
                    if fdesc != stdout:
                        break

                    data = os.read(stdout, 1024)
                    if iobuffer:
                        iobuffer.write(data)
                        iobuffer.flush()

                if proc.poll() is not None:
                    break

                if time.time() - t_start >= t_secs:
                    raise SUTTimeoutError(
                        "Timeout during reset command execution")

            self._logger.info("Reset command has been executed")

    def stop(self, timeout: float = 30, iobuffer: IOBuffer = None) -> None:
        self._stop = True

        t_secs = max(timeout, 0)

        try:
            # we don't need to handle run_command here, because when command
            # is running and client.close() is called, parent disconnect and
            # so command stops to run

            # wait until fetching file is ended
            if self._fetch_lock.locked():
                self._logger.info("Stop fetching file")

                start_t = time.time()
                while self._fetch_lock.locked():
                    time.sleep(0.05)
                    if time.time() - start_t >= t_secs:
                        raise SUTTimeoutError("Timed out during stop")

            if self._client:
                self._logger.info("Closing connection")
                self._client.close()
                self._logger.info("Connection closed")

            self._reset(timeout=timeout, iobuffer=iobuffer)
        except SSHException as err:
            raise SUTError(err)
        finally:
            self._shell = None
            self._stop = False

    def force_stop(
            self,
            timeout: float = 30,
            iobuffer: IOBuffer = None) -> None:
        self._stop = True

        try:
            if self._client:
                self._logger.info("Closing connection")
                self._client.close()
                self._logger.info("Connection closed")

            self._reset(timeout=timeout, iobuffer=iobuffer)
        except SSHException as err:
            raise SUTError(err)
        finally:
            self._shell = None
            self._stop = False

    def run_command(
            self,
            command: str,
            timeout: float = 3600,
            iobuffer: IOBuffer = None) -> dict:
        if not command:
            raise ValueError("command is empty")

        if not self.is_running:
            raise SUTError("SSH connection is not present")

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
            raise SUTError("SSH connection is not present")

        self._logger.info("Transfer file: %s", target_path)

        secs_t = max(timeout, 0)
        filename = os.path.basename(target_path)
        local_path = os.path.join(self._tmpdir, filename)
        data = b''

        try:
            with SCPClient(
                    self._client.get_transport(),
                    socket_timeout=secs_t) as scp:
                scp.get(target_path, local_path=local_path)

            with open(local_path, "rb") as lpath:
                data = lpath.read()
        except (SCPException, SSHException, EOFError) as err:
            if not self._stop:
                raise SUTError(err)
        except NameError:
            raise SUTError("scp package is not installed")
        except (TimeoutError, socket.timeout) as err:
            raise SUTTimeoutError(err)

        self._logger.info("File transfer completed")

        return data
