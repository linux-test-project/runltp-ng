"""
Test SUT implementations.
"""
import os
import pytest
from ltp.qemu import QemuSUT
from ltp.sut import KernelPanicError
from ltp.tests.sut import _TestSUT
from ltp.tests.sut import Printer


TEST_QEMU_IMAGE = os.environ.get("TEST_QEMU_IMAGE", None)
TEST_QEMU_PASSWORD = os.environ.get("TEST_QEMU_PASSWORD", None)


@pytest.mark.qemu
@pytest.mark.skipif(TEST_QEMU_IMAGE is None, reason="TEST_QEMU_IMAGE is not defined")
@pytest.mark.skipif(TEST_QEMU_PASSWORD is None, reason="TEST_QEMU_PASSWORD is not defined")
class _TestQemuSUT(_TestSUT):
    """
    Test Qemu SUT implementation.
    """

    def test_kernel_panic(self, sut):
        """
        Test kernel panic recognition.
        """
        iobuff = Printer()

        sut.communicate(iobuffer=iobuff)
        sut.run_command(
            "echo 'Kernel panic\nThis is a generic message' > /tmp/panic.txt",
            timeout=2,
            iobuffer=iobuff)

        with pytest.raises(KernelPanicError):
            sut.run_command(
                "cat /tmp/panic.txt",
                timeout=10,
                iobuffer=iobuff)


class TestQemuSUTISA(_TestQemuSUT):
    """
    Test QemuSUT implementation.
    """

    @pytest.fixture
    def sut(self, tmpdir):
        runner = QemuSUT()
        runner.setup(
            tmpdir=str(tmpdir),
            image=TEST_QEMU_IMAGE,
            password=TEST_QEMU_PASSWORD,
            serial="isa")

        yield runner

        if runner.is_running:
            runner.force_stop()


class TestQemuSUTVirtIO(_TestQemuSUT):
    """
    Test QemuSUT implementation.
    """

    @pytest.fixture
    def sut(self, tmpdir):
        runner = QemuSUT()
        runner.setup(
            tmpdir=str(tmpdir),
            image=TEST_QEMU_IMAGE,
            password=TEST_QEMU_PASSWORD,
            serial="virtio")

        yield runner

        if runner.is_running:
            runner.force_stop()
