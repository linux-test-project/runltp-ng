"""
Unittests for session module.
"""
import json
import os
import stat
import threading
import pytest
import ltp.events
from ltp.session import Session
from ltp.tempfile import TempDir


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
        self._messages = []
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

    def next_event(self) -> str:
        self._counter += 1
        return self._messages[self._counter]

    def _session_started(self, tmpdir) -> None:
        assert tmpdir.startswith(self._tmpdir)
        self._messages.append("session_started")

    def _session_completed(self, results) -> None:
        self._messages.append("session_completed")

    def _session_stopped(self) -> None:
        self._messages.append("session_stopped")

    def _session_error(self, err) -> None:
        assert err is not None
        self._messages.append("session_error")

    def _sut_start(self, sut_name) -> None:
        assert sut_name == self._sut_name
        self._messages.append("sut_start")

    def _sut_stop(self, sut_name) -> None:
        assert sut_name == self._sut_name
        self._messages.append("sut_stop")

    def _run_cmd_start(self, command) -> None:
        assert command == self._command
        self._messages.append("run_cmd_start")

    def _run_cmd_stop(self, command, stdout, returncode) -> None:
        assert command == self._command
        assert returncode == 0
        self._messages.append("run_cmd_stop")


class _TestSession:
    """
    Tests for Session implementation.
    """

    @pytest.fixture(autouse=True, scope="function")
    def setup(self):
        """
        Setup events before test.
        """
        ltp.events.reset()

    @pytest.fixture
    def ltpdir(self):
        """
        LTP install directory.
        """
        raise NotImplementedError()

    @pytest.fixture
    def suites(self):
        """
        LTP suites to run.
        """
        raise NotImplementedError()

    @pytest.fixture
    def sut_config(self):
        """
        SUT configuration to implement.
        """
        raise NotImplementedError()

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

        # create scenario_groups folder
        scenario_dir = ltpdir.mkdir("scenario_groups")

        scenario_def = scenario_dir.join("default")
        scenario_def.write("dirsuite0\ndirsuite1")

        scenario_def = scenario_dir.join("network")
        scenario_def.write("dirsuite2\ndirsuite3\ndirsuite4\ndirsuite5")

    @pytest.mark.usefixtures("prepare_tmpdir")
    @pytest.mark.parametrize("use_report", [True, False])
    @pytest.mark.parametrize("command", [None, "ls -1"])
    def test_run_single(
            self,
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
            session = Session()
            session.run_single(
                sut_config,
                report_path,
                suites,
                command,
                ltpdir,
                TempDir(root=tmpdir))

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
            tmpdir,
            sut_config,
            ltpdir):
        """
        Run a session using a specific sut configuration and skipping tests.
        """
        report_path = str(tmpdir / "report.json")

        try:
            session = Session()
            session.run_single(
                sut_config,
                report_path,
                ["dirsuite0", "dirsuite1"],
                None,
                ltpdir,
                TempDir(root=tmpdir),
                skip_tests=["dir02"])

            report_d = None
            with open(report_path, 'r') as report_f:
                report_d = json.loads(report_f.read())

            tests = [item['test_fqn'] for item in report_d["results"]]
            assert "dir02" not in tests
        finally:
            session.stop()

    @pytest.mark.usefixtures("prepare_tmpdir")
    def test_stop(self, tmpdir, sut_config, ltpdir, suites):
        """
        Run a session using a specific sut configuration.
        """
        report_path = str(tmpdir / "report.json")

        session = Session()

        def _threaded():
            session.stop(timeout=3)

        thread = threading.Thread(target=_threaded, daemon=True)

        def stop_exec_suites(test):
            thread.start()

        ltp.events.register("test_started", stop_exec_suites)

        tracer = EventsTracer(
            str(tmpdir),
            sut_config["name"],
            None)

        session.run_single(
            sut_config,
            report_path,
            suites,
            None,
            ltpdir,
            TempDir(tmpdir))

        thread.join(timeout=10)

        assert os.path.exists(report_path)
        assert tracer.next_event() == "session_started"
        assert tracer.next_event() == "sut_start"
        assert tracer.next_event() == "sut_stop"
        assert tracer.next_event() == "session_stopped"


class TestHostSession(_TestSession):
    """
    Test Session using host SUT.
    """

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


TEST_QEMU_IMAGE = os.environ.get("TEST_QEMU_IMAGE", None)
TEST_QEMU_PASSWORD = os.environ.get("TEST_QEMU_PASSWORD", None)


@pytest.mark.qemu
@pytest.mark.skipif(TEST_QEMU_IMAGE is None, reason="TEST_QEMU_IMAGE is not defined")
@pytest.mark.skipif(TEST_QEMU_PASSWORD is None, reason="TEST_QEMU_IMAGE is not defined")
class TestQemuSession(_TestSession):
    """
    Test Session using QemuSUT.
    """

    @pytest.fixture
    def ltpdir(self):
        return "/opt/ltp"

    @pytest.fixture
    def suites(self):
        return ["math", "watchqueue"]

    @pytest.fixture
    def sut_config(self):
        """
        Qemu SUT configuration.
        """
        config = {
            "name": "qemu",
            "image": TEST_QEMU_IMAGE,
            "password": TEST_QEMU_PASSWORD
        }
        return config
