"""
Unittests for main module.
"""
import os
import pwd
import time
import json
import pytest
import altp.main


class TestMain:
    """
    The the main module entry point.
    """
    # number of tests created inside temporary folder
    TESTS_NUM = 6

    @pytest.fixture(autouse=True)
    def prepare_tmpdir(self, tmpdir):
        """
        Prepare the temporary directory adding runtest folder.
        """
        # create simple testing suites
        content = ""
        for i in range(self.TESTS_NUM):
            content += f"test0{i} echo ciao\n"

        tmpdir.mkdir("testcases").mkdir("bin")
        runtest = tmpdir.mkdir("runtest")

        for i in range(3):
            suite = runtest / f"suite{i}"
            suite.write(content)

        # create a suite that is executing slower than the others
        content = ""
        for i in range(self.TESTS_NUM, self.TESTS_NUM * 2):
            content += f"test0{i} sleep 0.05\n"

        suite = runtest / f"slow_suite"
        suite.write(content)

        # enable parallelization for 'slow_suite'
        tests = {}
        for index in range(self.TESTS_NUM, self.TESTS_NUM * 2):
            name = f"test0{index}"
            tests[name] = {}

        metadata_d = {"tests": tests}
        metadata = tmpdir.mkdir("metadata") / "ltp.json"
        metadata.write(json.dumps(metadata_d))

        # create a suite printing environment variables
        suite = runtest / f"env_suite"
        suite.write("test_env echo -n $VAR0:$VAR1:$VAR2")

    def read_report(self, temp, tests_num) -> dict:
        """
        Check if report file contains the given number of tests.
        """
        name = pwd.getpwuid(os.getuid()).pw_name
        report = str(temp / f"runltp.{name}" / "latest" / "results.json")
        assert os.path.isfile(report)

        # read report and check if all suite's tests have been executed
        report_d = None
        with open(report, 'r') as report_f:
            report_d = json.loads(report_f.read())

        assert len(report_d["results"]) == tests_num

        return report_d

    def test_sut_plugins(self, tmpdir):
        """
        Test if SUT implementations are correctly loaded.
        """
        suts = []
        suts.append(tmpdir / "sutA.py")
        suts.append(tmpdir / "sutB.py")
        suts.append(tmpdir / "sutC.txt")

        for index in range(0, len(suts)):
            suts[index].write(
                "from altp.sut import SUT\n\n"
                f"class SUT{index}(SUT):\n"
                "    @property\n"
                "    def name(self) -> str:\n"
                f"        return 'mysut{index}'\n"
            )

        altp.main._discover_sut(str(tmpdir))

        assert len(altp.main.LOADED_SUT) == 2

        for index in range(0, len(altp.main.LOADED_SUT)):
            assert altp.main.LOADED_SUT[index].name == f"mysut{index}"

    def test_wrong_options(self):
        """
        Test wrong options.
        """
        cmd_args = [
            "--run-command1234", "ls"
        ]

        with pytest.raises(SystemExit) as excinfo:
            altp.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == 2

    def test_run_command(self, tmpdir):
        """
        Test --run-command option.
        """
        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--ltp-dir", str(tmpdir),
            "--tmp-dir", str(temp),
            "--run-command", "ls"
        ]

        with pytest.raises(SystemExit) as excinfo:
            altp.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == altp.main.RC_OK

    def test_run_command_timeout(self, tmpdir):
        """
        Test --run-command option with timeout.
        """
        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--ltp-dir", str(tmpdir),
            "--tmp-dir", str(temp),
            "--run-command", "ls",
            "--exec-timeout", "0"
        ]

        with pytest.raises(SystemExit) as excinfo:
            altp.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == altp.main.RC_ERROR

    def test_run_suite(self, tmpdir):
        """
        Test --run-suite option.
        """
        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--ltp-dir", str(tmpdir),
            "--tmp-dir", str(temp),
            "--run-suite", "suite0", "suite1", "suite2"
        ]

        with pytest.raises(SystemExit) as excinfo:
            altp.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == altp.main.RC_OK

        self.read_report(temp, self.TESTS_NUM * 3)

    def test_run_suite_timeout(self, tmpdir):
        """
        Test --run-suite option with timeout.
        """
        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--ltp-dir", str(tmpdir),
            "--tmp-dir", str(temp),
            "--run-suite", "suite0",
            "--suite-timeout", "0"
        ]

        with pytest.raises(SystemExit) as excinfo:
            altp.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == altp.main.RC_OK

        report_d = self.read_report(temp, self.TESTS_NUM)
        for param in report_d["results"]:
            assert param["test"]["passed"] == 0
            assert param["test"]["failed"] == 0
            assert param["test"]["broken"] == 0
            assert param["test"]["warnings"] == 0
            assert param["test"]["skipped"] == 1

    def test_run_suite_verbose(self, tmpdir, capsys):
        """
        Test --run-suite option with --verbose.
        """
        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--ltp-dir", str(tmpdir),
            "--tmp-dir", str(temp),
            "--run-suite", "suite0",
            "--verbose",
        ]

        with pytest.raises(SystemExit) as excinfo:
            altp.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == altp.main.RC_OK

        captured = capsys.readouterr()
        assert "ciao\n" in captured.out

    @pytest.mark.xfail(reason="This test passes if run alone. capsys bug?")
    def test_run_suite_no_colors(self, tmpdir, capsys):
        """
        Test --run-suite option with --no-colors.
        """
        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--ltp-dir", str(tmpdir),
            "--tmp-dir", str(temp),
            "--run-suite", "suite0",
            "--no-colors",
        ]

        with pytest.raises(SystemExit) as excinfo:
            altp.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == altp.main.RC_OK

        out, _ = capsys.readouterr()
        assert "test00: pass" in out

    def test_json_report(self, tmpdir):
        """
        Test --json-report option.
        """
        temp = tmpdir.mkdir("temp")
        report = str(tmpdir / "report.json")
        cmd_args = [
            "--ltp-dir", str(tmpdir),
            "--tmp-dir", str(temp),
            "--run-suite", "suite1",
            "--json-report", report
        ]

        with pytest.raises(SystemExit) as excinfo:
            altp.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == altp.main.RC_OK
        assert os.path.isfile(report)

        report_a = self.read_report(temp, self.TESTS_NUM)
        report_b = None
        with open(report, 'r') as report_f:
            report_b = json.loads(report_f.read())

        assert report_a == report_b

    def test_skip_tests(self, tmpdir):
        """
        Test --skip-tests option.
        """
        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--ltp-dir", str(tmpdir),
            "--tmp-dir", str(temp),
            "--run-suite", "suite0", "suite2",
            "--skip-tests", "test0[01]"
        ]

        with pytest.raises(SystemExit) as excinfo:
            altp.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == altp.main.RC_OK

        self.read_report(temp, (self.TESTS_NUM - 2) * 2)

    def test_skip_file(self, tmpdir):
        """
        Test --skip-file option.
        """
        skipfile = tmpdir / "skipfile"
        skipfile.write("test01\ntest02")

        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--ltp-dir", str(tmpdir),
            "--tmp-dir", str(temp),
            "--run-suite", "suite0", "suite2",
            "--skip-file", str(skipfile)
        ]

        with pytest.raises(SystemExit) as excinfo:
            altp.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == altp.main.RC_OK

        self.read_report(temp, (self.TESTS_NUM - 2) * 2)

    def test_skip_tests_and_file(self, tmpdir):
        """
        Test --skip-file option with --skip-tests.
        """
        skipfile = tmpdir / "skipfile"
        skipfile.write("test02\ntest03")

        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--ltp-dir", str(tmpdir),
            "--tmp-dir", str(temp),
            "--run-suite", "suite0", "suite2",
            "--skip-tests", "test0[01]",
            "--skip-file", str(skipfile)
        ]

        with pytest.raises(SystemExit) as excinfo:
            altp.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == altp.main.RC_OK

        self.read_report(temp, (self.TESTS_NUM - 4) * 2)

    def test_workers(self, tmpdir):
        """
        Test --workers option.
        """
        temp = tmpdir.mkdir("temp")

        # run on single worker
        cmd_args = [
            "--ltp-dir", str(tmpdir),
            "--tmp-dir", str(temp),
            "--run-suite", "slow_suite",
            "--workers", "1",
        ]

        first_t = 0
        start_t = time.time()
        with pytest.raises(SystemExit) as excinfo:
            altp.main.run(cmd_args=cmd_args)
        first_t = time.time() - start_t

        assert excinfo.value.code == altp.main.RC_OK
        self.read_report(temp, self.TESTS_NUM)

        # run on multiple workers
        cmd_args = [
            "--ltp-dir", str(tmpdir),
            "--tmp-dir", str(temp),
            "--run-suite", "slow_suite",
            "--workers", str(os.cpu_count()),
        ]

        second_t = 0
        start_t = time.time()
        with pytest.raises(SystemExit) as excinfo:
            altp.main.run(cmd_args=cmd_args)
        second_t = time.time() - start_t

        assert excinfo.value.code == altp.main.RC_OK
        self.read_report(temp, self.TESTS_NUM)

        assert second_t < first_t

    def test_sut_help(self):
        """
        Test "--sut help" command and check if SUT class(es) are loaded.
        """
        cmd_args = [
            "--sut", "help"
        ]

        with pytest.raises(SystemExit) as excinfo:
            altp.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == altp.main.RC_OK
        assert len(altp.main.LOADED_SUT) > 0

    def test_env(self, tmpdir):
        """
        Test --env option.
        """
        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--ltp-dir", str(tmpdir),
            "--tmp-dir", str(temp),
            "--run-suite", "env_suite",
            "--env", "VAR0=0:VAR1=1:VAR2=2"
        ]

        with pytest.raises(SystemExit) as excinfo:
            altp.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == altp.main.RC_OK

        report_d = self.read_report(temp, 1)
        assert report_d["results"][0]["test"]["log"] == "0:1:2"
