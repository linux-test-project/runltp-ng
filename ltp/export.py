"""
.. module:: export
    :platform: Linux
    :synopsis: module containing exporters definition

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import json
import logging
from ltp import LTPException


class ExporterError(LTPException):
    """
    Raised when an error occurs during Exporter operations.
    """


class Exporter:
    """
    A class used to export Results into report file.
    """

    def save_file(self, results: list, path: str) -> None:
        """
        Save report into a file by taking information from SUT and testing
        results.
        :param results: list of suite results to export.
        :type results: list(SuiteResults)
        :param path: path of the file to save.
        :type path: str
        """
        raise NotImplementedError()


class JSONExporter(Exporter):
    """
    Export testing results into a JSON file.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger("ltp.json")

    # pylint: disable=too-many-locals
    def save_file(self, results: list, path: str) -> None:
        if not results:
            raise ValueError("results is empty")

        if not path:
            raise ValueError("path is empty")

        if os.path.exists(path):
            raise ExporterError(f"'{path}' already exists")

        self._logger.info("Exporting JSON report into %s", path)

        # add results information
        data_suites = []

        for result in results:
            data_suite = {}
            data_suite["name"] = result.suite.name
            data_suite["sut"] = {
                "distro": result.distro,
                "distro_ver": result.distro_ver,
                "kernel": result.kernel,
                "arch": result.arch
            }
            data_suite["results"] = {
                "exec_time": result.exec_time,
                "failed": result.failed,
                "passed": result.passed,
                "broken": result.broken,
                "skipped": result.skipped,
                "warnings": result.warnings
            }

            data_tests = []
            for test_report in result.tests_results:
                data_test = {}
                data_test["name"] = test_report.test.name
                data_test["command"] = test_report.test.command
                data_test["arguments"] = test_report.test.arguments
                data_test["stdout"] = test_report.stdout
                data_test["returncode"] = test_report.return_code
                data_test["exec_time"] = test_report.exec_time
                data_test["failed"] = test_report.failed
                data_test["passed"] = test_report.passed
                data_test["broken"] = test_report.broken
                data_test["skipped"] = test_report.skipped
                data_test["warnings"] = test_report.warnings
                data_tests.append(data_test)

            data_suite["tests"] = data_tests
            data_suites.append(data_suite)

        data = {}
        data["suites"] = data_suites

        with open(path, "w+", encoding='UTF-8') as outfile:
            json.dump(data, outfile, indent=4)

        self._logger.info("Report exported")
