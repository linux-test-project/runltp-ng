"""
Test SUT implementations.
"""
import os
import time
import pytest
from ltp.ssh import SSHSUT
from ltp.sut import IOBuffer
from ltp.sut import KernelPanicError
from ltp.tests.sut import _TestSUT

TEST_SSH_USERNAME = os.environ.get("TEST_SSH_USERNAME", None)
TEST_SSH_PASSWORD = os.environ.get("TEST_SSH_PASSWORD", None)
TEST_SSH_KEY_FILE = os.environ.get("TEST_SSH_KEY_FILE", None)


class _TestSSHSUT(_TestSUT):
    """
    Test SSHSUT implementation using username/password.
    """

    @pytest.fixture
    def config(self):
        """
        Base configuration to connect to SUT.
        """
        raise NotImplementedError()

    @pytest.fixture
    def sut(self, config):
        sut = SSHSUT()
        sut.setup(**config)

        yield sut

        if sut.is_running:
            sut.force_stop()

    def test_cwd(self, config):
        """
        Test CWD constructor argument.
        """
        kwargs = dict(cwd="/etc")
        kwargs.update(config)

        sut = SSHSUT()
        sut.setup(**kwargs)
        sut.communicate()

        ret = sut.run_command("test -f fstab", timeout=1)
        assert ret["returncode"] == 0

    def test_env(self, config):
        """
        Test ENV constructor argument.
        """
        kwargs = dict(
            env=dict(FILE="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"))
        kwargs.update(config)

        sut = SSHSUT()
        sut.setup(**kwargs)
        sut.communicate()

        ret = sut.run_command("echo -n $FILE", timeout=1)
        assert ret["returncode"] == 0
        assert ret["stdout"] == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

    def test_reset_command(self, config):
        """
        Test reset_command option.
        """
        kwargs = dict(reset_cmd="echo ciao")
        kwargs.update(config)

        sut = SSHSUT()
        sut.setup(**kwargs)
        sut.communicate()

        class MyBuffer(IOBuffer):
            data = ""

            def write(self, data: str) -> None:
                self.data = data
                # wait for data inside the buffer
                time.sleep(0.1)

            def flush(self) -> None:
                return

        buffer = MyBuffer()
        sut.stop(timeout=1, iobuffer=buffer)

        assert buffer.data == 'ciao\n'

    @pytest.mark.parametrize("enable", ["0", "1"])
    def test_sudo(self, config, enable):
        """
        Test sudo parameter.
        """
        kwargs = dict(sudo=enable)
        kwargs.update(config)

        sut = SSHSUT()
        sut.setup(**kwargs)
        sut.communicate()
        ret = sut.run_command("whoami", timeout=1)

        if enable == "1":
            assert ret["stdout"] == "root\n"
        else:
            assert ret["stdout"] != "root\n"

    def test_kernel_panic(self, sut):
        """
        Test kernel panic recognition.
        """
        sut.communicate()

        with pytest.raises(KernelPanicError):
            sut.run_command(
                "echo 'Kernel panic\nThis is a generic message'",
                timeout=10)


@pytest.mark.ssh
@pytest.mark.skipif(TEST_SSH_USERNAME is None, reason="TEST_SSH_USERNAME is not defined")
@pytest.mark.skipif(TEST_SSH_PASSWORD is None, reason="TEST_SSH_PASSWORD is not defined")
class TestSSHSUTPassword(_TestSSHSUT):
    """
    Test SSHSUT implementation using username/password.
    """

    @pytest.fixture
    def config(self, tmpdir):
        return dict(
            tmpdir=str(tmpdir),
            host="localhost",
            port=22,
            user=TEST_SSH_USERNAME,
            password=TEST_SSH_PASSWORD)


@pytest.mark.ssh
@pytest.mark.skipif(TEST_SSH_USERNAME is None, reason="TEST_SSH_USERNAME is not defined")
@pytest.mark.skipif(TEST_SSH_KEY_FILE is None, reason="TEST_SSH_KEY_FILE is not defined")
class TestSSHSUTKeyfile(_TestSSHSUT):
    """
    Test SSHSUT implementation using username/password.
    """

    @pytest.fixture
    def config(self, tmpdir):
        return dict(
            tmpdir=str(tmpdir),
            host="localhost",
            port=22,
            user=TEST_SSH_USERNAME,
            key_file=TEST_SSH_KEY_FILE)
