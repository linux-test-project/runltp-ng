"""
Test SUT implementations.
"""
import os
import pytest
from ltp.qemu import QemuSUT
from ltp.tests.sut import _TestSUT


TEST_QEMU_IMAGE = os.environ.get("TEST_QEMU_IMAGE", None)
TEST_QEMU_PASSWORD = os.environ.get("TEST_QEMU_PASSWORD", None)


@pytest.mark.qemu
@pytest.mark.skipif(TEST_QEMU_IMAGE is None, reason="TEST_QEMU_IMAGE is not defined")
@pytest.mark.skipif(TEST_QEMU_PASSWORD is None, reason="TEST_QEMU_IMAGE is not defined")
class TestQemuSUTISA(_TestSUT):
    """
    Test QemuSUT implementation.
    """

    @pytest.fixture
    def sut(self, tmpdir):
        runner = QemuSUT(
            tmpdir=str(tmpdir),
            image=TEST_QEMU_IMAGE,
            password=TEST_QEMU_PASSWORD,
            serial="isa")

        yield runner

        if runner.is_running:
            runner.stop()

@pytest.mark.qemu
@pytest.mark.skipif(TEST_QEMU_IMAGE is None, reason="TEST_QEMU_IMAGE is not defined")
@pytest.mark.skipif(TEST_QEMU_PASSWORD is None, reason="TEST_QEMU_IMAGE is not defined")
class TestQemuSUTVirtIO(_TestSUT):
    """
    Test QemuSUT implementation.
    """

    @pytest.fixture
    def sut(self, tmpdir):
        runner = QemuSUT(
            tmpdir=str(tmpdir),
            image=TEST_QEMU_IMAGE,
            password=TEST_QEMU_PASSWORD,
            serial="virtio")

        yield runner

        if runner.is_running:
            runner.stop()
