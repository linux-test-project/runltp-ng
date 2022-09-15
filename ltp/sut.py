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


class SUTTimeoutError(LTPException):
    """
    Raised when timeout error occurs in SUT.
    """


class IOBuffer:
    """
    IO stdout buffer. The API is similar to ``IO`` types.
    """

    def write(self, data: bytes) -> None:
        """
        Write data.
        """
        raise NotImplementedError()

    def flush(self) -> None:
        """
        Flush data.
        """
        raise NotImplementedError()


TAINED_MSG = [
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
        raise NotImplementedError()

    def get_tained_info(self) -> set:
        """
        Return information about kernel if tained.
        :returns: set(int, list[str]),
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

    def force_stop(self, timeout: float = 30, iobuffer: IOBuffer = None) -> None:
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


# pylint: disable=too-many-locals
def collect_sysinfo(sut: SUT) -> dict:
    """
    Collect system information from SUT.
    :returns: dict

        {
            "distro": str,
            "distro_ver": str,
            "kernel": str,
            "arch": str,
            "cpu" : str,
            "swap" : str,
            "ram" : str,
            "kernel_tained" : set(int, list(str)),
        }

    """
    # create suite results
    def _run_cmd(cmd: str) -> str:
        """
        Run command, check for returncode and return command's stdout.
        """
        ret = sut.run_command(cmd, timeout=3)
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

    tained = _run_cmd("cat /proc/sys/kernel/tainted")

    tained_num = len(TAINED_MSG)
    code = int(tained.rstrip())
    bits = format(code, f"0{tained_num}b")[::-1]

    messages = []
    for i in range(0, tained_num):
        if bits[i] == "1":
            msg = TAINED_MSG[i]
            messages.append(msg)

    ret = {
        "distro": distro,
        "distro_ver": distro_ver,
        "kernel": kernel,
        "arch": arch,
        "cpu": cpu,
        "swap": swap_m.group('swap'),
        "ram": mem_m.group('memory'),
        "kernel_tained": (code, messages)
    }

    return ret
