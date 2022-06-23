"""
.. module:: metadata
    :platform: Linux
    :synopsis: module handling input files such as runtest and metadata

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import logging
from ltp import LTPException
from ltp.suite import Suite
from ltp.suite import Test


class MetadataError(LTPException):
    """
    Raised if an error occurs when reading metadata.
    """


class Metadata:
    """
    This is an implementation used to load testing suite metadata
    rapresentation. Testing suites are usually defined inside a file that
    contains all tests information.
    """

    def read_suite(self, suite_name: str) -> Suite:
        """
        Read a testing suite and return a Suite object.
        :param suite_name: testing suite name
        :type suite_name: str
        :returns: dict
        """
        raise NotImplementedError()


class Runtest(Metadata):
    """
    Handle runtest files.
    """

    def __init__(self, runtest_folder: str) -> None:
        """
        :param runtest_folder: LTP runtest directory
        :type runtest_folder: str
        """
        self._logger = logging.getLogger("ltp.runtest")

        if not os.path.isdir(runtest_folder):
            raise ValueError("runtest_folder is not a directory")

        self._suites = {}
        self._runtest_folder = runtest_folder

    # pylint: disable=too-many-locals
    def read_suite(self, suite_name: str) -> Suite:
        if not suite_name:
            raise ValueError("suite_name is empty")

        if not self._suites:
            self._logger.debug("Reading suites from %s", self._runtest_folder)

            for suite in os.listdir(self._runtest_folder):
                subdir = os.path.join(self._runtest_folder, suite)
                if not os.path.isfile(subdir):
                    continue

                self._suites[suite] = subdir

            self._logger.debug(self._suites)

        if suite_name not in self._suites:
            raise ValueError(f"{suite_name} suite is not available")

        suite_path = self._suites[suite_name]

        self._logger.info("Collecting testing suite: %s", suite_name)

        lines = []
        try:
            with open(suite_path, "r", encoding='UTF-8') as data:
                lines = data.readlines()
        except IOError as err:
            raise MetadataError(err)

        tests = []
        for line in lines:
            if not line.strip() or line.strip().startswith("#"):
                continue

            self._logger.debug("test declaration: %s", line)

            parts = line.split()
            if len(parts) < 2:
                raise MetadataError("Test declaration is not defining command")

            test_name = parts[0]
            test_cmd = parts[1]
            test_args = []

            if len(parts) >= 3:
                test_args = parts[2:]

            test = Test(test_name, test_cmd, test_args)
            tests.append(test)

            self._logger.debug("test: %s", test)

        self._logger.debug("Collected %d tests", len(tests))

        suite = Suite(suite_name, tests)

        self._logger.debug(suite)
        self._logger.info("Collected testing suite")

        return suite
