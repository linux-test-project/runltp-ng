"""
.. module:: data
    :platform: Linux
    :synopsis: module containing input data handling

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import logging
from ltp.suite import Test
from ltp.suite import Suite


LOGGER = logging.getLogger("ltp.data")


def read_runtest(suite_name: str, content: str) -> Suite:
    """
    It reads a runtest file content and it returns a Suite object.
    :param suite_name: name of the test suite
    :type suite_name: str
    :param content: content of the runtest file
    :type content: str
    :returns: Suite
    """
    if not content:
        raise ValueError("content is empty")

    LOGGER.info("collecting testing suite: %s", suite_name)

    tests = []
    lines = content.split('\n')
    for line in lines:
        if not line.strip() or line.strip().startswith("#"):
            continue

        LOGGER.debug("test declaration: %s", line)

        parts = line.split()
        if len(parts) < 2:
            raise ValueError("Test declaration is not defining command")

        test_name = parts[0]
        test_cmd = parts[1]
        test_args = []

        if len(parts) >= 3:
            test_args = parts[2:]

        test = Test(test_name, test_cmd, test_args)
        tests.append(test)

        LOGGER.debug("test: %s", test)

    LOGGER.debug("collected tests: %d", len(tests))

    suite = Suite(suite_name, tests)

    LOGGER.debug(suite)
    LOGGER.info("collected testing suite: %s", suite_name)

    return suite
