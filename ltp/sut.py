"""
.. module:: sut
    :platform: Linux
    :synopsis: sut definition

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import re
from ltp import LTPException


class SUTError(LTPException):
    """
    Raised when an error occurs in SUT.
    """


class SUTTimeoutError(SUTError):
    """
    Raised when timeout error occurs in SUT.
    """


class KernelPanicError(SUTError):
    """
    Raised during kernel panic.
    """


class IOBuffer:
    """
    IO stdout buffer. The API is similar to ``IO`` types.
    """

    def write(self, data: str) -> None:
        """
        Write data.
        """
        raise NotImplementedError()

    def flush(self) -> None:
        """
        Flush data.
        """
        raise NotImplementedError()


TAINTED_MSG = [
    "proprietary module was loaded",
    "module was force loaded",
    "kernel running on an out of specification system",
    "module was force unloaded",
    "processor reported a Machine Check Exception (MCE)",
    "bad page referenced or some unexpected page flags",
    "taint requested by userspace application",
    "kernel died recently, i.e. there was an OOPS or BUG",
    "ACPI table overridden by user",
    "kernel issued warning",
    "staging driver was loaded",
    "workaround for bug in platform firmware applied",
    "externally-built (“out-of-tree”) module was loaded",
    "unsigned module was loaded",
    "soft lockup occurred",
    "kernel has been live patched",
    "auxiliary taint, defined for and used by distros",
    "kernel was built with the struct randomization plugin"
]


class SUT:
    """
    SUT abstraction class. It could be a remote host, a local host, a virtual
    machine instance, etc.
    """

    def setup(self, **kwargs: dict) -> None:
        """
        Initialize SUT using configuration dictionary.
        :param kwargs: SUT configuration
        :type kwargs: dict
        """
        raise NotImplementedError()

    @property
    def config_help(self) -> dict:
        """
        Associate each configuration option with a help message.
        This is used by the main menu application to generate --help message.
        :returns: dict
        """
        raise NotImplementedError()

    @property
    def is_running(self) -> bool:
        """
        Return True if SUT is running.
        """
        raise NotImplementedError()

    @property
    def name(self) -> str:
        """
        Name of the SUT.
        """
        raise NotImplementedError()

    def ping(self) -> float:
        """
        If SUT is replying and it's available, ping will return time needed to
        wait for SUT reply.
        :returns: float
        """
        raise NotImplementedError()

    def communicate(self,
                    timeout: float = 3600,
                    iobuffer: IOBuffer = None) -> None:
        """
        Start communicating with the SUT.
        :param timeout: timeout to complete communication in seconds
        :type timeout: float
        :param iobuffer: buffer used to write SUT stdout
        :type iobuffer: IOBuffer
        """
        raise NotImplementedError()

    def stop(self, timeout: float = 30, iobuffer: IOBuffer = None) -> None:
        """
        Stop the current SUT session.
        :param timeout: timeout to complete in seconds
        :type timeout: float
        :param iobuffer: buffer used to write SUT stdout
        :type iobuffer: IOBuffer
        """
        raise NotImplementedError()

    def force_stop(self,
                   timeout: float = 30,
                   iobuffer: IOBuffer = None) -> None:
        """
        Force stopping the current SUT session.
        :param timeout: timeout to complete in seconds
        :type timeout: float
        :param iobuffer: buffer used to write SUT stdout
        :type iobuffer: IOBuffer
        """
        raise NotImplementedError()

    def run_command(self,
                    command: str,
                    timeout: float = 3600,
                    iobuffer: IOBuffer = None) -> dict:
        """
        Run command on target.
        :param command: command to execute
        :type command: str
        :param timeout: timeout before stopping execution. Default is 3600
        :type timeout: float
        :param iobuffer: buffer used to write SUT stdout
        :type iobuffer: IOBuffer
        :returns: dictionary containing command execution information

            {
                "command": <str>,
                "timeout": <float>,
                "returncode": <int>,
                "stdout": <str>,
                "exec_time": <float>,
            }

            If None is returned, then callback failed.
        """
        raise NotImplementedError()

    def fetch_file(
            self,
            target_path: str,
            timeout: float = 3600) -> bytes:
        """
        Fetch file from target path and return data from target path.
        :param target_path: path of the file to download from target
        :type target_path: str
        :param timeout: timeout before stopping data transfer. Default is 3600
        :type timeout: float
        :returns: bytes contained in target_path
        """
        raise NotImplementedError()

    def ensure_communicate(
            self,
            timeout: float = 3600,
            iobuffer: IOBuffer = None,
            retries: int = 10,
            force: bool = False) -> None:
        """
        Ensure that `communicate` is completed, retrying as many times we
        want in case of `LTPException` error. After each `communicate` error
        the SUT is stopped and a new communication is tried.
        :param timeout: timeout to complete communication in seconds
        :type timeout: float
        :param iobuffer: buffer used to write SUT stdout
        :type iobuffer: IOBuffer
        :param retries: number of times we retry communicating with SUT
        :type retries: int
        :param force: use `force_stop` instead of `stop` before communicating
            again with the SUT
        :type force: bool
        """
        retries = max(retries, 1)

        for retry in range(retries):
            try:
                self.communicate(
                    timeout=timeout,
                    iobuffer=iobuffer)

                break
            except LTPException as err:
                if retry >= retries - 1:
                    raise err

                if force:
                    self.force_stop(timeout=timeout, iobuffer=iobuffer)
                else:
                    self.stop(timeout=timeout, iobuffer=iobuffer)

    def get_info(self) -> dict:
        """
        Return SUT information.
        :returns: dict

            {
                "distro": str,
                "distro_ver": str,
                "kernel": str,
                "arch": str,
                "cpu" : str,
                "swap" : str,
                "ram" : str,
            }

        """
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
        cpu = _run_cmd("uname -p")
        meminfo = _run_cmd("cat /proc/meminfo")

        swap_m = re.search(r'SwapTotal:\s+(?P<swap>\d+\s+kB)', meminfo)
        if not swap_m:
            raise SUTError("Can't read swap information from /proc/meminfo")

        mem_m = re.search(r'MemTotal:\s+(?P<memory>\d+\s+kB)', meminfo)
        if not mem_m:
            raise SUTError("Can't read memory information from /proc/meminfo")

        ret = {
            "distro": distro,
            "distro_ver": distro_ver,
            "kernel": kernel,
            "arch": arch,
            "cpu": cpu,
            "swap": swap_m.group('swap'),
            "ram": mem_m.group('memory')
        }

        return ret

    def get_tainted_info(self) -> set:
        """
        Return information about kernel if tainted.
        :returns: set(int, list[str]),
        """
        ret = self.run_command("cat /proc/sys/kernel/tainted", timeout=3)
        if ret["returncode"] != 0:
            raise SUTError("Can't read tainted kernel information")

        stdout = ret["stdout"].rstrip()

        tainted_num = len(TAINTED_MSG)
        code = int(stdout.rstrip())
        bits = format(code, f"0{tainted_num}b")[::-1]

        messages = []
        for i in range(0, tainted_num):
            if bits[i] == "1":
                msg = TAINTED_MSG[i]
                messages.append(msg)

        return code, messages
