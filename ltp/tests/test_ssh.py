"""
Test SUT implementations.
"""
import os
import pytest
from ltp.ssh import SSHSUT
from ltp.tests.sut import _TestSUT


TEST_SSH_USERNAME = os.environ.get("TEST_SSH_USERNAME", None)
TEST_SSH_PASSWORD = os.environ.get("TEST_SSH_PASSWORD", None)
TEST_SSH_KEY_FILE = os.environ.get("TEST_SSH_KEY_FILE", None)


@pytest.mark.ssh
@pytest.mark.skipif(TEST_SSH_USERNAME is None, reason="TEST_SSH_USERNAME is not defined")
@pytest.mark.skipif(TEST_SSH_PASSWORD is None, reason="TEST_SSH_PASSWORD is not defined")
class TestSSHSUTPassword(_TestSUT):
    """
    Test SSHSUT implementation using username/password.
    """

    @pytest.fixture
    def sut(self, tmpdir):
        sut = SSHSUT(
            tmpdir=str(tmpdir),
            host="localhost",
            port=22,
            user=TEST_SSH_USERNAME,
            password=TEST_SSH_PASSWORD)

        yield sut

        if sut.is_running:
            sut.stop()

    def test_cwd(self, tmpdir):
        """
        Test CWD constructor argument.
        """
        sut = SSHSUT(
            tmpdir=str(tmpdir),
            host="localhost",
            port=22,
            user=TEST_SSH_USERNAME,
            password=TEST_SSH_PASSWORD,
            cwd="/etc")
        sut.communicate()

        ret = sut.run_command("test -f fstab", timeout=1)
        assert ret["returncode"] == 0

    def test_env(self, tmpdir):
        """
        Test ENV constructor argument.
        """
        sut = SSHSUT(
            tmpdir=str(tmpdir),
            host="localhost",
            port=22,
            user=TEST_SSH_USERNAME,
            password=TEST_SSH_PASSWORD,
            env=dict(FILE="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"))
        sut.communicate()

        ret = sut.run_command("echo -n $FILE", timeout=1)
        assert ret["returncode"] == 0
        assert ret["stdout"] == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


@pytest.mark.ssh
@pytest.mark.skipif(TEST_SSH_USERNAME is None, reason="TEST_SSH_USERNAME is not defined")
@pytest.mark.skipif(TEST_SSH_KEY_FILE is None, reason="TEST_SSH_KEY_FILE is not defined")
class TestSSHSUTKeyfile(_TestSUT):
    """
    Test SSHSUT implementation using username/password.
    """

    @pytest.fixture
    def sut(self, tmpdir):
        sut = SSHSUT(
            tmpdir=str(tmpdir),
            host="localhost",
            port=22,
            user=TEST_SSH_USERNAME,
            key_file=TEST_SSH_KEY_FILE)

        yield sut

        if sut.is_running:
            sut.stop()

    def test_cwd(self, tmpdir):
        """
        Test CWD constructor argument.
        """
        sut = SSHSUT(
            tmpdir=str(tmpdir),
            host="localhost",
            port=22,
            user=TEST_SSH_USERNAME,
            key_file=TEST_SSH_KEY_FILE,
            cwd="/etc")
        sut.communicate()

        ret = sut.run_command("test -f fstab", timeout=1)
        assert ret["returncode"] == 0

    def test_env(self, tmpdir):
        """
        Test ENV constructor argument.
        """
        sut = SSHSUT(
            tmpdir=str(tmpdir),
            host="localhost",
            port=22,
            user=TEST_SSH_USERNAME,
            key_file=TEST_SSH_KEY_FILE,
            env=dict(FILE="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"))
        sut.communicate()

        ret = sut.run_command("echo -n $FILE", timeout=1)
        assert ret["returncode"] == 0
        assert ret["stdout"] == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
