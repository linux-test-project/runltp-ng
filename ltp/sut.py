"""
.. module:: sut
    :platform: Linux
    :synopsis: sut definition

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
from ltp import LTPException


class SUTError(LTPException):
    """
    Raised when an error occurs in SUT.
    """


class SUTTimeoutError(LTPException):
    """
    Raised when timeout error occurs in SUT.
    """


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

    def communicate(self, timeout: float = 3600) -> None:
        """
        Start communicating with the SUT.
        :param timeout: timeout to complete communication in seconds
        :type timeout: float
        """
        raise NotImplementedError()

    def stop(self, timeout: float = 30) -> None:
        """
        Stop the current SUT session.
        :param timeout: timeout to complete in seconds
        :type timeout: float
        """
        raise NotImplementedError()

    def force_stop(self, timeout: float = 30) -> None:
        """
        Force stopping the current SUT session.
        :param timeout: timeout to complete in seconds
        :type timeout: float
        """
        raise NotImplementedError()

    def run_command(self, command: str, timeout: float = 3600) -> dict:
        """
        Run command on target.
        :param command: command to execute
        :param timeout: timeout before stopping execution. Default is 3600
        :type timeout: float
        :returns: dictionary containing command execution information

            {
                "command": <str>,
                "timeout": <int>,
                "returncode": <int>,
                "stdout": <str>,
                "exec_time": <int>,
            }

            If None is returned, then callback failed.
        """
        raise NotImplementedError()

    def fetch_file(
            self,
            target_path: str,
            local_path: str,
            timeout: float = 3600) -> None:
        """
        Fetch file from target path and download it in the specified
        local path.
        :param target_path: path of the file to download from target
        :type target_path: str
        :param local_path: path of the downloaded file on local host
        :type local_path: str
        :param timeout: timeout before stopping data transfer. Default is 3600
        :type timeout: float
        """
        raise NotImplementedError()
