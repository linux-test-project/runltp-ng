"""
Test SUT implementations.
"""
import pytest
import logging
from ltp.host import HostSUT
from ltp.tests.sut import _TestSUT


class Printer:
    """
    stdout printer.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger("test.host")
        self._line = ""

    def write(self, data):
        data_str = data.decode(encoding="utf-8", errors="ignore")

        lines = data_str.split('\n')
        for line in lines[:-1]:
            self._line += line
            self._logger.info(self._line)
            self._line = ""

        self._line = lines[-1]

        if data_str.endswith('\n') and self._line:
            self._logger.info(self._line)
            self._line = ""

    def flush(self):
        pass


@pytest.fixture
def sut():
    sut = HostSUT(iobuffer=Printer())
    yield sut

    if sut.is_running:
        sut.stop()

class TestHostSUT(_TestSUT):
    """
    Test HostSUT implementation.
    """

    def test_cwd(self, tmpdir):
        """
        Test CWD constructor argument.
        """
        myfile = tmpdir / "myfile"
        myfile.write("runltp-ng tests")

        sut = HostSUT(cwd=str(tmpdir))
        sut.communicate()

        ret = sut.run_command("cat myfile", timeout=2)
        assert ret["returncode"] == 0
        assert ret["stdout"] == "runltp-ng tests"

    def test_env(self, tmpdir):
        """
        Test ENV constructor argument.
        """
        myfile = tmpdir / "myfile"
        myfile.write("runltp-ng tests")

        sut = HostSUT(cwd=str(tmpdir), env=dict(FILE=str(myfile)))
        sut.communicate()

        ret = sut.run_command("cat $FILE", timeout=2)
        assert ret["returncode"] == 0
        assert ret["stdout"] == "runltp-ng tests"
