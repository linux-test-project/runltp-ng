"""
Unittest for temporary module.
"""
import os
import time
import pathlib
import pytest
from ltp.tempfile import TempRotator


class TestTempRotator:
    """
    Test the TempRotator class implementation.
    """

    def test_constructor(self):
        """
        Test TempRotator constructor.
        """
        with pytest.raises(ValueError):
            TempRotator("this_folder_doesnt_exist")

    def test_rotate(self, tmpdir):
        """
        Test rotate method.
        """
        max_rotate = 5
        plus_rotate = 5

        currdir = str(tmpdir)
        rotator = TempRotator(currdir, max_rotate=max_rotate)

        paths = []
        for _ in range(0, max_rotate + plus_rotate):
            path = rotator.rotate()
            paths.append(path)

            # force cache IO operations
            os.sync()

        # just wait and re-sync to be sure about files removal
        time.sleep(0.5)
        os.sync()

        sorted_paths = sorted(
            pathlib.Path(rotator._tmpbase).iterdir(),
            key=os.path.getmtime)

        latest = None
        for path in sorted_paths:
            if path.name == "latest":
                latest = path
                break

        assert latest is not None
        assert os.readlink(str(path)) == paths[-1]

        paths_dir = [
            str(path) for path in sorted_paths
            if path.name != "latest"
        ]

        assert list(set(paths[plus_rotate:]) - set(paths_dir)) == []
