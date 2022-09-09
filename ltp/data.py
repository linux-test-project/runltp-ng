"""
.. module:: data
    :platform: Linux
    :synopsis: module containing input data handling

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import logging

LOGGER = logging.getLogger("ltp.data")


class Suite:
    """
    Testing suite definition class.
    """

    def __init__(self, name: str, tests: list) -> None:
        """
        :param name: name of the testing suite
        :type name: str
        :param tests: tests of the suite
        :type tests: list
        """
        self._name = name
        self._tests = tests

    def __repr__(self) -> str:
        return \
            f"name: '{self._name}', " \
            f"tests: {self._tests}"

    @property
    def name(self):
        """
        Name of the testing suite.
        """
        return self._name

    @property
    def tests(self):
        """
        Tests definitions.
        """
        return self._tests


class Test:
    """
    Test definition class.
    """

    def __init__(self, name: str, cmd: str, args: list) -> None:
        """
        :param name: name of the test
        :type name: str
        :param cmd: command to execute
        :type cmd: str
        :param args: list of arguments
        :type args: list(str)
        """
        self._name = name
        self._cmd = cmd
        self._args = args

    def __repr__(self) -> str:
        return \
            f"name: '{self._name}', " \
            f"commmand: '{self._cmd}', " \
            f"arguments: {self._args}"

    @property
    def name(self):
        """
        Name of the test.
        """
        return self._name

    @property
    def command(self):
        """
        Command to execute test.
        """
        return self._cmd

    @property
    def arguments(self):
        """
        Arguments of the command.
        """
        return self._args


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
