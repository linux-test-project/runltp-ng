"""
.. module:: utils
    :platform: Linux
    :synopsis: module containing utilities implementations
.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import time
from ltp import LTPException


class LTPTimeoutError(LTPException):
    """
    Default class raised when timeout is reached.
    """


class Timeout:
    """
    Timeout class handler. Use it as following:

        with Timeout(10.0) as timeout:
            while True:
                do_task()
                timeout.check("error msg", MyException)

    """

    def __init__(self, timeout: float) -> None:
        self._timeout = max(timeout, 0)
        self._end = None

    def __enter__(self) -> None:
        self._end = time.time() + self._timeout

        return self

    def __exit__(self, ttype, value, traceback) -> None:
        self._end = None

    def check(self, err_msg: str = None, exc: Exception = None):
        """
        Check if time is out.
        """
        if not self._end:
            self._end = time.time() + self._timeout

        if self._end > time.time():
            return

        message = "" if err_msg is None else err_msg
        exception = LTPTimeoutError if exc is None else exc

        raise exception(message)
