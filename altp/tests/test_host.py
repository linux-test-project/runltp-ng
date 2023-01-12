"""
Unittests for host SUT implementations.
"""
import pytest
from altp.host import HostSUT
from altp.tests.sut import _TestSUT
from altp.tests.sut import Printer


pytestmark = pytest.mark.asyncio


@pytest.fixture
async def sut():
    sut = HostSUT()
    sut.setup()

    yield sut

    if await sut.is_running:
        await sut.stop()


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

    async def test_cwd(self, tmpdir):
        """
        Test CWD constructor argument.
        """
        myfile = tmpdir / "myfile"
        myfile.write("runltp-ng tests")

        sut = HostSUT()
        sut.setup(cwd=str(tmpdir))
        await sut.communicate(iobuffer=Printer())

        ret = await sut.run_command("cat myfile", iobuffer=Printer())
        assert ret["returncode"] == 0
        assert ret["stdout"] == "runltp-ng tests"

    async def test_env(self, tmpdir):
        """
        Test ENV constructor argument.
        """
        myfile = tmpdir / "myfile"
        myfile.write("runltp-ng tests")

        sut = HostSUT()
        sut.setup(cwd=str(tmpdir), env=dict(FILE=str(myfile)))
        await sut.communicate(iobuffer=Printer())

        ret = await sut.run_command("cat $FILE", iobuffer=Printer())
        assert ret["returncode"] == 0
        assert ret["stdout"] == "runltp-ng tests"

    async def test_fetch_file_stop(self):
        pytest.skip(reason="Coroutines don't support I/O file handling")
