"""
Test SUT implementations.
"""
import os
import pytest
import logging
from ltp.qemu import QemuSUT
from ltp.tests.sut import _TestSUT


TEST_QEMU_IMAGE = os.environ.get("TEST_QEMU_IMAGE", None)
TEST_QEMU_PASSWORD = os.environ.get("TEST_QEMU_PASSWORD", None)


class Printer:
    """
    stdout printer.
    """
    def __init__(self) -> None:
        self._logger = logging.getLogger("test.qemu")
        self._line = ""

    def write(self, data):
        self._line += data.decode(encoding="utf-8", errors="ignore")
        if data == b'\n':
            self._logger.info(self._line[:-1])
            self._line = ""

    def flush(self):
        pass


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
            iobuffer=Printer(),
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
            iobuffer=Printer(),
            serial="virtio")

        yield runner

        if runner.is_running:
            runner.stop()
