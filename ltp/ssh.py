"""
.. module:: ssh
    :platform: Linux
    :synopsis: module defining SSH SUT

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import time
import select
import socket
import logging
import threading
import importlib
import subprocess
from ltp.sut import SUT
from ltp.sut import IOBuffer
from ltp.sut import SUTError
from ltp.sut import SUTTimeoutError
from ltp.sut import KernelPanicError
from ltp.utils import Timeout

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
    def __init__(self) -> None:
        self._logger = logging.getLogger("ltp.ssh")
        self._tmpdir = None
        self._host = "localhost"
        self._port = 22
        self._user = "root"
        self._password = None
        self._pkey = None
        self._reset_cmd = None
        self._sudo = 0
        self._env = None
        self._cwd = None
        self._cmd_lock = threading.Lock()
        self._comm_lock = threading.Lock()
        self._fetch_lock = threading.Lock()
        self._stop = False
        self._client = None

    def setup(self, **kwargs: dict) -> None:
        if not importlib.util.find_spec('paramiko'):
            raise SUTError("'paramiko' library is not available")

        if not importlib.util.find_spec('scp'):
            raise SUTError("'scp' library is not available")

        self._logger.info("Initialize SUT")

        self._tmpdir = kwargs.get("tmpdir", None)
        self._host = kwargs.get("host", "localhost")
        self._user = kwargs.get("user", "root")
        self._password = kwargs.get("password", None)
        key_file = kwargs.get("key_file", None)
        hostkey_policy = kwargs.get("hostkey_policy", "auto")
        known_hosts = kwargs.get("known_hosts", None)
        self._pkey = None
        self._reset_cmd = kwargs.get("reset_cmd", None)
        self._env = kwargs.get("env", None)
        self._cwd = kwargs.get("cwd", None)
        self._stop = False
        self._client = None

        try:
            self._port = int(kwargs.get("port", "22"))

            if 1 > self._port > 65535:
                raise ValueError()
        except ValueError:
            raise SUTError("'port' must be an integer between 1-65535")

        try:
            self._sudo = int(kwargs.get("sudo", 0)) == 1
        except ValueError:
            raise SUTError("'sudo' must be 0 or 1")

        if hostkey_policy not in ["auto", "missing", "reject"]:
            raise SUTError(f"'{hostkey_policy}' policy is not available")

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

        if not self._tmpdir or not os.path.isdir(self._tmpdir):
            raise SUTError(
                f"Temporary directory doesn't exist: {self._tmpdir}")

        if not self._host:
            raise SUTError("host is empty")

        if not self._user:
            raise SUTError("user is empty")

        if key_file and not os.path.isfile(key_file):
            raise SUTError("private key doesn't exist")

        if key_file:
            self._logger.info("Reading key file: %s", key_file)
            self._pkey = RSAKey.from_private_key_file(key_file)

    @property
    def config_help(self) -> dict:
        return dict(
            host="IP address of the SUT (default: localhost)",
            port="TCP port of the service (default: 22)",
            user="name of the user (default: root)",
            password="root password",
            timeout="connection timeout in seconds (default: 10)",
            key_file="private key location",
            hostkey_policy="host key policy - auto | missing | reject. (default: auto)",
            known_hosts="known_hosts file (default: ~/.ssh/known_hosts)",
            reset_command="command to reset the remote SUT",
            sudo="use sudo to access to root shell (default: 0)",
        )

    @property
    def name(self) -> str:
        return "ssh"

    @property
    def is_running(self) -> bool:
        if self._client and self._client.get_transport():
            return self._client.get_transport().is_active()

        return False

    def ping(self) -> float:
        if not self.is_running:
            raise SUTError("SSH connection is not present")

        ret = self.run_command("test .", timeout=1)
        reply_t = ret["exec_time"]

        return reply_t

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

            with Timeout(timeout) as timer:
                while True:
                    events = poller.poll(0.1)
                    for fdesc, _ in events:
                        if fdesc != stdout:
                            break

                        data = os.read(stdout, 1024)
                        if iobuffer:
                            rdata = data.decode(
                                encoding="utf-8",
                                errors="ignore")

                            iobuffer.write(rdata)
                            iobuffer.flush()

                    if proc.poll() is not None:
                        break

                    timer.check(
                        err_msg="Timeout during reset command execution",
                        exc=SUTTimeoutError)

            self._logger.info("Reset command has been executed")

    def stop(self, timeout: float = 30, iobuffer: IOBuffer = None) -> None:
        self._stop = True

        try:
            if self._client:
                self._logger.info("Closing connection")
                self._client.close()
                self._logger.info("Connection closed")

            # wait until fetching file is ended
            if self._fetch_lock.locked():
                self._logger.info("Stop fetching file")

                with Timeout(timeout) as timer:
                    while self._fetch_lock.locked():
                        time.sleep(1e-6)
                        timer.check(
                            err_msg="Timed out during stop",
                            exc=SUTTimeoutError)

            self._reset(timeout=timeout, iobuffer=iobuffer)
        except SSHException as err:
            raise SUTError(err)
        finally:
            self._stop = False

    def force_stop(
            self,
            timeout: float = 30,
            iobuffer: IOBuffer = None) -> None:
        self.stop(timeout=timeout, iobuffer=iobuffer)

    def _create_command(self, cmd: str) -> str:
        """
        Create command to send to SSH client.
        """
        script = ""

        if self._cwd:
            script += f"cd {self._cwd};"

        if self._env:
            for key, value in self._env.items():
                script += f"export {key}={value};"

        script += cmd

        if self._sudo:
            script = f"sudo /bin/sh -c '{script}'"

        return script

    # pylint: disable=too-many-locals
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
            t_end = 0
            retcode = -1
            stdout_str = ""

            try:
                self._logger.info("Running command: %s", repr(command))

                exec_cmd = self._create_command(command)

                self._logger.debug(repr(exec_cmd))

                t_start = time.time()
                _, stdout, _ = self._client.exec_command(
                    exec_cmd,
                    timeout=timeout)

                stdout.channel.set_combine_stderr(True)
                stdout_str = ""
                panic = False

                while True:
                    line = stdout.readline()
                    if not line:
                        break

                    if "Kernel panic" in line:
                        panic = True

                    stdout_str += line
                    if iobuffer:
                        iobuffer.write(line)
                        iobuffer.flush()

                t_end = time.time() - t_start

                if panic:
                    raise KernelPanicError()

                with Timeout(10) as timer:
                    while not stdout.channel.exit_status_ready():
                        timer.check(
                            err_msg="Timeout when waiting for exit code",
                            exc=SUTTimeoutError)

                retcode = stdout.channel.recv_exit_status()
            except socket.timeout:
                raise SUTTimeoutError(
                    f"Timeout during command execution: {repr(command)}")
            except SSHException as err:
                if not self._stop:
                    raise SUTError(err)

            ret = {
                "command": command,
                "timeout": timeout,
                "returncode": retcode,
                "stdout": stdout_str,
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

        with self._fetch_lock:
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
            except (TimeoutError, socket.timeout) as err:
                raise SUTTimeoutError(err)

            self._logger.info("File transfer completed")

            return data
