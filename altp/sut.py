"""
.. module:: sut
    :platform: Linux
    :synopsis: sut definition

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import re
import asyncio
from altp import LTPException


class SUTError(LTPException):
    """
    Raised when an error occurs in SUT.
    """


class KernelPanicError(SUTError):
    """
    Raised during kernel panic.
    """


class IOBuffer:
    """
    IO stdout buffer. The API is similar to ``IO`` types.
    """

    async def write(self, data: str) -> None:
        """
        Write data.
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
    def name(self) -> str:
        """
        Name of the SUT.
        """
        raise NotImplementedError()

    @property
    def parallel_execution(self) -> bool:
        """
        If True, SUT supports commands parallel execution.
        """
        raise NotImplementedError()

    @property
    async def is_running(self) -> bool:
        """
        Return True if SUT is running.
        """
        raise NotImplementedError()

    async def ping(self) -> float:
        """
        If SUT is replying and it's available, ping will return time needed to
        wait for SUT reply.
        :returns: float
        """
        raise NotImplementedError()

    async def communicate(self, iobuffer: IOBuffer = None) -> None:
        """
        Start communicating with the SUT.
        :param iobuffer: buffer used to write SUT stdout
        :type iobuffer: IOBuffer
        """
        raise NotImplementedError()

    async def stop(self, iobuffer: IOBuffer = None) -> None:
        """
        Stop the current SUT session.
        :param iobuffer: buffer used to write SUT stdout
        :type iobuffer: IOBuffer
        """
        raise NotImplementedError()

    async def run_command(
            self,
            command: str,
            iobuffer: IOBuffer = None) -> dict:
        """
        Coroutine to run command on target.
        :param command: command to execute
        :type command: str
        :param iobuffer: buffer used to write SUT stdout
        :type iobuffer: IOBuffer
        :returns: dictionary containing command execution information

            {
                "command": <str>,
                "returncode": <int>,
                "stdout": <str>,
                "exec_time": <float>,
            }

            If None is returned, then callback failed.
        """
        raise NotImplementedError()

    async def fetch_file(self, target_path: str) -> bytes:
        """
        Fetch file from target path and return data from target path.
        :param target_path: path of the file to download from target
        :type target_path: str
        :returns: bytes contained in target_path
        """
        raise NotImplementedError()

    async def ensure_communicate(
            self,
            iobuffer: IOBuffer = None,
            retries: int = 10) -> None:
        """
        Ensure that `communicate` is completed, retrying as many times we
        want in case of `LTPException` error. After each `communicate` error
        the SUT is stopped and a new communication is tried.
        :param iobuffer: buffer used to write SUT stdout
        :type iobuffer: IOBuffer
        :param retries: number of times we retry communicating with SUT
        :type retries: int
        """
        retries = max(retries, 1)

        for retry in range(retries):
            try:
                await self.communicate(iobuffer=iobuffer)
                break
            except LTPException as err:
                if retry >= retries - 1:
                    raise err

                await self.stop(iobuffer=iobuffer)

    async def get_info(self) -> dict:
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
        async def _run_cmd(cmd: str) -> str:
            """
            Run command, check for returncode and return command's stdout.
            """
            ret = await self.run_command(cmd)
            if ret["returncode"] != 0:
                raise SUTError(f"Can't read information from SUT: {cmd}")

            stdout = ret["stdout"].rstrip()

            return stdout

        distro, \
            distro_ver, \
            kernel, \
            arch, \
            cpu, \
            meminfo = await asyncio.gather(*[
                _run_cmd(". /etc/os-release; echo \"$ID\""),
                _run_cmd(". /etc/os-release; echo \"$VERSION_ID\""),
                _run_cmd("uname -s -r -v"),
                _run_cmd("uname -m"),
                _run_cmd("uname -p"),
                _run_cmd("cat /proc/meminfo")
            ])

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

    async def get_tainted_info(self) -> tuple:
        """
        Return information about kernel if tainted.
        :returns: set(int, list[str]),
        """
        ret = await self.run_command("cat /proc/sys/kernel/tainted")
        if ret["returncode"] != 0:
            raise SUTError("Can't read tainted kernel information")

        stdout = ret["stdout"].rstrip()

        tainted_num = len(TAINED_MSG)
        code = int(stdout.rstrip())
        bits = format(code, f"0{tainted_num}b")[::-1]

        messages = []
        for i in range(0, tainted_num):
            if bits[i] == "1":
                msg = TAINED_MSG[i]
                messages.append(msg)

        return code, messages
