"""
Unittests for session module.
"""
import os
import stat
import json
import queue
import pytest
import ltp
from ltp.session import Session
from ltp.tempfile import TempDir
from ltp.host import HostSUT


class EventsTracer:
    """
    Trace events and check they all have been called.
    """

    def __init__(
            self,
            tmpdir: str,
            sut_name: str,
            command: str) -> None:
        self._counter = -1
        self._messages = queue.Queue()
        self._tmpdir = tmpdir
        self._sut_name = sut_name
        self._command = command

        ltp.events.register("session_started", self._session_started)
        ltp.events.register("session_completed", self._session_completed)
        ltp.events.register("session_stopped", self._session_stopped)
        ltp.events.register("session_error", self._session_error)
        ltp.events.register("sut_start", self._sut_start)
        ltp.events.register("sut_stop", self._sut_stop)
        ltp.events.register("run_cmd_start", self._run_cmd_start)
        ltp.events.register("run_cmd_stop", self._run_cmd_stop)
        ltp.events.register("suite_timeout", self._suite_timeout)

    def next_event(self) -> str:
        self._counter += 1
        return self._messages.get()

    def _session_started(self, tmpdir) -> None:
        assert tmpdir.startswith(self._tmpdir)
        self._messages.put("session_started")

    def _session_completed(self, results) -> None:
        self._messages.put("session_completed")

    def _session_stopped(self) -> None:
        self._messages.put("session_stopped")

    def _session_error(self, err) -> None:
        assert err is not None
        self._messages.put("session_error")

    def _sut_start(self, sut_name) -> None:
        assert sut_name == self._sut_name
        self._messages.put("sut_start")

    def _sut_stop(self, sut_name) -> None:
        assert sut_name == self._sut_name
        self._messages.put("sut_stop")

    def _run_cmd_start(self, command) -> None:
        assert command == self._command
        self._messages.put("run_cmd_start")

    def _run_cmd_stop(self, command, stdout, returncode) -> None:
        assert command == self._command
        assert returncode == 0
        self._messages.put("run_cmd_stop")

    def _suite_timeout(self, suite_name, timeout) -> None:
        self._messages.put("suite_timeout")


class TestSession:
    """
    Tests for Session implementation.
    """

    @pytest.fixture(autouse=True, scope="function")
    def setup(self):
        """
        Setup events before test.
        """
        ltp.events.start_event_loop()

        yield

        ltp.events.stop_event_loop()
        ltp.events.reset()

    @pytest.fixture
    def sut(self):
        """
        Current implemented SUT in the default runltp-ng implementation.
        """
        return HostSUT()

    @pytest.fixture
    def ltpdir(self, tmpdir):
        return str(tmpdir / "ltp")

    @pytest.fixture
    def suites(self):
        return ["dirsuite0", "dirsuite1"]

    @pytest.fixture
    def sut_config(self):
        config = {"name": "host"}
        return config

    @pytest.fixture
    def prepare_tmpdir(self, tmpdir):
        """
        Prepare the temporary directory adding suites and tests.
        """
        # create testcases folder
        ltpdir = tmpdir.mkdir("ltp")
        testcases = ltpdir.mkdir("testcases").mkdir("bin")

        script_sh = testcases.join("script.sh")
        script_sh.write(
            '#!/bin/bash\n'
            'echo ""\n'
            'echo ""\n'
            'echo "Summary:"\n'
            'echo "passed   $1"\n'
            'echo "failed   $2"\n'
            'echo "broken   $3"\n'
            'echo "skipped  $4"\n'
            'echo "warnings $5"\n'
        )

        st = os.stat(str(script_sh))
        os.chmod(str(script_sh), st.st_mode | stat.S_IEXEC)

        # create runtest folder
        runtest = ltpdir.mkdir("runtest")

        suitefile = runtest.join("dirsuite0")
        suitefile.write("dir01 script.sh 1 0 0 0 0")

        suitefile = runtest.join("dirsuite1")
        suitefile.write("dir02 script.sh 0 1 0 0 0")

        suitefile = runtest.join("dirsuite2")
        suitefile.write("dir03 script.sh 0 0 0 1 0")

        suitefile = runtest.join("dirsuite3")
        suitefile.write("dir04 script.sh 0 0 1 0 0")

        suitefile = runtest.join("dirsuite4")
        suitefile.write("dir05 script.sh 0 0 0 0 1")

        suitefile = runtest.join("sleep")
        suitefile.write("sleep01 sleep 1\nsleep02 sleep 2\nsleep03 sleep 3")

        # create scenario_groups folder
        scenario_dir = ltpdir.mkdir("scenario_groups")

        scenario_def = scenario_dir.join("default")
        scenario_def.write("dirsuite0\ndirsuite1")

        scenario_def = scenario_dir.join("network")
        scenario_def.write("dirsuite2\ndirsuite3\ndirsuite4\ndirsuite5")

    @pytest.mark.usefixtures("prepare_tmpdir")
    def test_run_cmd(self, sut, tmpdir, sut_config, ltpdir):
        """
        Run a session without suites but only one command run.
        """
        tracer = EventsTracer(
            str(tmpdir),
            sut_config["name"],
            "ls -l")

        try:
            session = Session(
                sut=sut,
                sut_config=sut_config,
                ltpdir=ltpdir,
                tmpdir=str(tmpdir))

            retcode = session.run_single(command="ls -l")

            assert retcode == Session.RC_OK
            assert tracer.next_event() == "session_started"
            assert tracer.next_event() == "sut_start"
            assert tracer.next_event() == "run_cmd_start"
            assert tracer.next_event() == "run_cmd_stop"
            assert tracer.next_event() == "sut_stop"
        finally:
            session.stop()

    @pytest.mark.usefixtures("prepare_tmpdir")
    @pytest.mark.parametrize("use_report", [True, False])
    @pytest.mark.parametrize("command", [None, "ls -1"])
    def test_run_single(
            self,
            sut,
            tmpdir,
            use_report,
            suites,
            command,
            sut_config,
            ltpdir):
        """
        Run a session using a specific sut configuration.
        """
        report_path = None
        if use_report:
            report_path = str(tmpdir / "report.json")

        tracer = EventsTracer(
            str(tmpdir),
            sut_config["name"],
            command)

        try:
            session = Session(
                sut=sut,
                sut_config=sut_config,
                ltpdir=ltpdir,
                tmpdir=str(tmpdir))

            retcode = session.run_single(
                report_path=report_path,
                suites=suites,
                command=command)

            assert retcode == Session.RC_OK
            assert tracer.next_event() == "session_started"
            assert tracer.next_event() == "sut_start"

            if command:
                assert tracer.next_event() == "run_cmd_start"
                assert tracer.next_event() == "run_cmd_stop"

            assert tracer.next_event() == "sut_stop"

            if suites:
                if use_report:
                    assert os.path.isfile(report_path)
            else:
                if use_report:
                    assert not os.path.exists(report_path)

            assert tracer.next_event() == "session_completed"
        finally:
            session.stop()

    @pytest.mark.usefixtures("prepare_tmpdir")
    def test_skip_tests(
            self,
            sut,
            tmpdir,
            sut_config,
            ltpdir):
        """
        Run a session using a specific sut configuration and skipping tests.
        """
        report_path = str(tmpdir / "report.json")

        try:
            session = Session(
                sut=sut,
                sut_config=sut_config,
                ltpdir=ltpdir,
                tmpdir=str(tmpdir),
                skip_tests="dir0[12]|dir0(1|3)|dir05")

            retcode = session.run_single(
                report_path=report_path,
                suites=[
                    "dirsuite0",
                    "dirsuite1",
                    "dirsuite2",
                    "dirsuite3",
                    "dirsuite4"
                ])

            report_d = None
            with open(report_path, 'r') as report_f:
                report_d = json.loads(report_f.read())

            assert retcode == Session.RC_OK
            tests = [item['test_fqn'] for item in report_d["results"]]
            assert "dir01" not in tests
            assert "dir02" not in tests
            assert "dir03" not in tests
            assert "dir04" in tests
            assert "dir05" not in tests
        finally:
            session.stop()

    @pytest.mark.usefixtures("prepare_tmpdir")
    def test_stop(self, sut, tmpdir, sut_config, ltpdir, suites):
        """
        Run a session using a specific sut configuration.
        """
        report_path = str(tmpdir / "report.json")

        session = Session(
            sut=sut,
            sut_config=sut_config,
            ltpdir=ltpdir,
            tmpdir=str(tmpdir))

        def stop_exec_suites(test):
            session.stop(timeout=3)

        ltp.events.register("test_started", stop_exec_suites)

        tracer = EventsTracer(
            str(tmpdir),
            sut_config["name"],
            None)

        retcode = session.run_single(report_path=report_path, suites=suites)

        assert retcode == Session.RC_OK
        assert os.path.exists(report_path)
        assert tracer.next_event() == "session_started"
        assert tracer.next_event() == "sut_start"
        assert tracer.next_event() == "sut_stop"
        assert tracer.next_event() == "session_stopped"

    @pytest.mark.usefixtures("prepare_tmpdir")
    def test_suite_timeout_report(self, sut, tmpdir, sut_config, ltpdir):
        """
        Test suite timeout and verify that JSON report is created in any way.
        """
        report_path = str(tmpdir / "report.json")

        session = Session(
            sut=sut,
            sut_config=sut_config,
            ltpdir=ltpdir,
            tmpdir=str(tmpdir),
            suite_timeout=0)

        tracer = EventsTracer(
            str(tmpdir),
            sut_config["name"],
            None)

        retcode = session.run_single(
            suites=["sleep"],
            report_path=report_path)

        assert retcode == Session.RC_TIMEOUT
        assert os.path.exists(report_path)
        assert tracer.next_event() == "session_started"
        assert tracer.next_event() == "sut_start"
        assert tracer.next_event() == "suite_timeout"
        assert tracer.next_event() == "sut_stop"
        assert tracer.next_event() == "session_completed"

    def test_env(self, sut, tmpdir, sut_config, ltpdir):
        """
        Run a session without suites but only one command run.
        """
        report_path = tmpdir / "report.json"

        ltpdir = tmpdir.mkdir("ltp")
        script_sh = ltpdir.mkdir("testcases").mkdir("bin") / "script.sh"
        script_sh.write("#!/bin/sh\necho -n $VAR0:$VAR1")

        st = os.stat(str(script_sh))
        os.chmod(str(script_sh), st.st_mode | stat.S_IEXEC)

        suite = ltpdir.mkdir("runtest") / "suite"
        suite.write("test script.sh")

        try:
            session = Session(
                sut=sut,
                sut_config=sut_config,
                ltpdir=ltpdir,
                tmpdir=str(tmpdir),
                env=dict(VAR0="0", VAR1="1"))

            retcode = session.run_single(
                report_path=report_path,
                suites=["suite"])

            assert retcode == Session.RC_OK
            assert os.path.isfile(report_path)

            report_d = None
            with open(report_path, 'r') as report_f:
                report_d = json.loads(report_f.read())

            assert len(report_d["results"]) > 0
            assert report_d["results"][0]["test"]["log"] == "0:1"
        finally:
            session.stop()
