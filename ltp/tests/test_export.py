"""
Unit tests for Exporter implementations.
"""
import json
import pytest
from ltp.data import Test
from ltp.data import Suite
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
                arch="x86_64",
                cpu="x86_64",
                swap="10 kB",
                ram="1000 kB"),
        ]

        output = tmpdir / "output.json"

        exporter = JSONExporter()
        exporter.save_file(suite_res, str(output))

        data = None
        with open(str(output), 'r') as json_data:
            data = json.load(json_data)

        assert len(data["results"]) == 3
        assert data["results"][0] == {
            "test": {
                "command": "ls",
                "arguments": "",
                "failed": 0,
                "passed": 1,
                "broken": 0,
                "skipped": 0,
                "warnings": 0,
                "duration": 1,
                "result": "pass",
                "log": "folder\nfile.txt",
                "retval": [
                    "0"
                ],
            },
            "status": "pass",
            "test_fqn": "ls0",
        }
        assert data["results"][1] == {
            "test": {
                "command": "ls",
                "arguments": "-l",
                "failed": 0,
                "passed": 1,
                "broken": 0,
                "skipped": 0,
                "warnings": 0,
                "duration": 1,
                "result": "pass",
                "log": "folder\nfile.txt",
                "retval": [
                    "0"
                ],
            },
            "status": "pass",
            "test_fqn": "ls1",
        }
        assert data["results"][2] == {
            "test": {
                "command": "ls",
                "arguments": "--error",
                "failed": 1,
                "passed": 0,
                "broken": 0,
                "skipped": 0,
                "warnings": 0,
                "duration": 1,
                "result": "fail",
                "log": "",
                "retval": [
                    "1"
                ],
            },
            "status": "fail",
            "test_fqn": "ls2",
        }

        assert data["environment"] == {
            "distribution_version": "15.3",
            "distribution": "openSUSE-Leap",
            "kernel": "5.17",
            "arch": "x86_64",
            "cpu": "x86_64",
            "swap": "10 kB",
            "RAM": "1000 kB",
        }
        assert data["stats"] == {
            "runtime": 3,
            "passed": 2,
            "failed": 1,
            "broken": 0,
            "skipped": 0,
            "warnings": 0,
        }
