"""
Unit tests for Exporter implementations.
"""
import json
import pytest
from ltp.suite import Test
from ltp.suite import Suite
from ltp.results import SuiteResults, TestResults
from ltp.export import JSONExporter


class TestJSONExporter:
    """
    Test JSONExporter class implementation.
    """

    def test_save_file_bad_args(self):
        """
        Test save_file method with bad arguments.
        """
        exporter = JSONExporter()

        with pytest.raises(ValueError):
            exporter.save_file(list(), "")

        with pytest.raises(ValueError):
            exporter.save_file(None, "")

        with pytest.raises(ValueError):
            exporter.save_file([0, 1], None)

    def test_save_file(self, tmpdir):
        """
        Test save_file method.
        """
        # create suite/test metadata objects
        tests = [
            Test("ls0", "ls", ""),
            Test("ls1", "ls", "-l"),
            Test("ls2", "ls", "--error")
        ]
        suite0 = Suite("ls_suite0", tests)
        suite1 = Suite("ls_suite1", tests)

        # create results objects
        tests_res = [
            TestResults(
                test=tests[0],
                failed=0,
                passed=1,
                broken=0,
                skipped=0,
                warnings=0,
                exec_time=1,
                retcode=0,
                stdout="folder\nfile.txt"
            ),
            TestResults(
                test=tests[1],
                failed=0,
                passed=1,
                broken=0,
                skipped=0,
                warnings=0,
                exec_time=1,
                retcode=0,
                stdout="folder\nfile.txt"
            ),
            TestResults(
                test=tests[2],
                failed=1,
                passed=0,
                broken=0,
                skipped=0,
                warnings=0,
                exec_time=1,
                retcode=1,
                stdout=""
            ),
        ]

        suite_res = [
            SuiteResults(
                suite=suite0,
                tests=tests_res,
                distro="openSUSE-Leap",
                distro_ver="15.3",
                kernel="5.17",
                arch="x86_64"),
            SuiteResults(
                suite=suite1,
                tests=tests_res,
                distro="openSUSE-Leap",
                distro_ver="15.3",
                kernel="5.17",
                arch="x86_64"),
        ]

        output = tmpdir / "output.json"

        exporter = JSONExporter()
        exporter.save_file(suite_res, str(output))

        data = None
        with open(str(output), 'r') as json_data:
            data = json.load(json_data)

        # first suite
        assert len(data["suites"]) == 2
        assert data["suites"][0]["name"] == "ls_suite0"
        assert data["suites"][0]["sut"] == {
            "distro": "openSUSE-Leap",
            "distro_ver": "15.3",
            "kernel": "5.17",
            "arch": "x86_64"
        }
        assert data["suites"][0]["results"] == {
            "exec_time": 3,
            "passed": 2,
            "failed": 1,
            "broken": 0,
            "skipped": 0,
            "warnings": 0,
        }
        assert data["suites"][0]["tests"] == [
            {
                "name": "ls0",
                "command": "ls",
                "arguments": "",
                "failed": 0,
                "passed": 1,
                "broken": 0,
                "skipped": 0,
                "warnings": 0,
                "exec_time": 1,
                "returncode": 0,
                "stdout": "folder\nfile.txt",
            },
            {
                "name": "ls1",
                "command": "ls",
                "arguments": "-l",
                "failed": 0,
                "passed": 1,
                "broken": 0,
                "skipped": 0,
                "warnings": 0,
                "exec_time": 1,
                "returncode": 0,
                "stdout": "folder\nfile.txt",
            },
            {
                "name": "ls2",
                "command": "ls",
                "arguments": "--error",
                "failed": 1,
                "passed": 0,
                "broken": 0,
                "skipped": 0,
                "warnings": 0,
                "exec_time": 1,
                "returncode": 1,
                "stdout": "",
            },
        ]

        # second suite
        assert data["suites"][1]["name"] == "ls_suite1"
        assert data["suites"][1]["sut"] == {
            "distro": "openSUSE-Leap",
            "distro_ver": "15.3",
            "kernel": "5.17",
            "arch": "x86_64"
        }
        assert data["suites"][1]["results"] == {
            "exec_time": 3,
            "passed": 2,
            "failed": 1,
            "broken": 0,
            "skipped": 0,
            "warnings": 0,
        }
        assert data["suites"][1]["tests"] == [
            {
                "name": "ls0",
                "command": "ls",
                "arguments": "",
                "failed": 0,
                "passed": 1,
                "broken": 0,
                "skipped": 0,
                "warnings": 0,
                "exec_time": 1,
                "returncode": 0,
                "stdout": "folder\nfile.txt",
            },
            {
                "name": "ls1",
                "command": "ls",
                "arguments": "-l",
                "failed": 0,
                "passed": 1,
                "broken": 0,
                "skipped": 0,
                "warnings": 0,
                "exec_time": 1,
                "returncode": 0,
                "stdout": "folder\nfile.txt",
            },
            {
                "name": "ls2",
                "command": "ls",
                "arguments": "--error",
                "failed": 1,
                "passed": 0,
                "broken": 0,
                "skipped": 0,
                "warnings": 0,
                "exec_time": 1,
                "returncode": 1,
                "stdout": "",
            },
        ]
