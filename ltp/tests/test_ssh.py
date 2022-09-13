"""
Test SUT implementations.
"""
import os
import time
import pytest
from ltp.ssh import SSHSUT
from ltp.sut import IOBuffer
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
        sut = SSHSUT(**config)

        yield sut

        if sut.is_running:
            sut.stop()

    def test_cwd(self, config):
        """
        Test CWD constructor argument.
        """
        kwargs = dict(cwd="/etc")
        kwargs.update(config)

        sut = SSHSUT(**kwargs)
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

        sut = SSHSUT(**kwargs)
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

        sut = SSHSUT(**kwargs)
        sut.communicate()

        class MyBuffer(IOBuffer):
            data = bytes()

            def write(self, data: bytes) -> None:
                self.data = data
                # wait for data inside the buffer
                time.sleep(0.1)

            def flush(self) -> None:
                return

        buffer = MyBuffer()
        sut.stop(timeout=1, iobuffer=buffer)

        assert buffer.data == b'ciao\n'


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
class TestSSHSUTKeyfile(_TestSUT):
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
