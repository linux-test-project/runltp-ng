"""
Unittests for utilities.
"""
import time
import pytest
from ltp.utils import Timeout
from ltp.utils import LTPTimeoutError


class TestTimeout:
    """
    Tests for Timeout class.
    """

    def test_no_timeout(self):
        """
        Test class without timeout.
        """
        with Timeout(1) as timeout:
            time.sleep(0.01)
            timeout.check()

    def test_timeout_default_exception(self):
        """
        Test a timeout.
        """
        with pytest.raises(LTPTimeoutError, match=''):
            with Timeout(0.01) as timeout:
                time.sleep(0.01)
                timeout.check()

    def test_timeout_custom_exception(self):
        """
        Test a timeout with custom exception.
        """
        with pytest.raises(TimeoutError):
            with Timeout(0.01) as timeout:
                time.sleep(0.01)
                timeout.check(exc=TimeoutError)

    def test_timeout_custom_message(self):
        """
        Test a timeout with custom message.
        """
        with pytest.raises(LTPTimeoutError, match='error message'):
            with Timeout(0.01) as timeout:
                time.sleep(0.01)
                timeout.check(err_msg='error message')

    def test_timeout_custom_all(self):
        """
        Test a timeout with custom message and custom exception.
        """
        with pytest.raises(TimeoutError, match='error message'):
            with Timeout(0.01) as timeout:
                time.sleep(0.01)
                timeout.check(err_msg='error message', exc=TimeoutError)

    def test_no_with(self):
        """
        Test class without 'with' block.
        """
        timeout = Timeout(1)
        time.sleep(0.01)
        timeout.check()
