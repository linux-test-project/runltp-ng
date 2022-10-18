"""
Test SUT implementations.
"""
import pytest
from ltp.host import HostSUT
from ltp.tests.sut import _TestSUT
from ltp.tests.sut import Printer


@pytest.fixture
def sut():
    sut = HostSUT()

    yield sut

    if sut.is_running:
        sut.stop()


class TestHostSUT(_TestSUT):
    """
    Test HostSUT implementation.
    """

    @pytest.fixture
    def sut_stop_sleep(self, request):
        """
        Host SUT test doesn't require time sleep in `test_stop_communicate`.
        """
        return request.param * 0

    def test_cwd(self, tmpdir):
        """
        Test CWD constructor argument.
        """
        myfile = tmpdir / "myfile"
        myfile.write("runltp-ng tests")

        sut = HostSUT()
        sut.setup(cwd=str(tmpdir))
        sut.communicate(iobuffer=Printer())

        ret = sut.run_command("cat myfile", timeout=2, iobuffer=Printer())
        assert ret["returncode"] == 0
        assert ret["stdout"] == "runltp-ng tests"

    def test_env(self, tmpdir):
        """
        Test ENV constructor argument.
        """
        myfile = tmpdir / "myfile"
        myfile.write("runltp-ng tests")

        sut = HostSUT()
        sut.setup(cwd=str(tmpdir), env=dict(FILE=str(myfile)))
        sut.communicate(iobuffer=Printer())

        ret = sut.run_command("cat $FILE", timeout=2, iobuffer=Printer())
        assert ret["returncode"] == 0
        assert ret["stdout"] == "runltp-ng tests"
