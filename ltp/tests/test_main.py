"""
Unittests for main module.
"""
import ltp.main


def test_sut_plugins(tmpdir):
    """
    Test if SUT implementations are correctly loaded.
    """
    suts = []
    suts.append(tmpdir / "sutA.py")
    suts.append(tmpdir / "sutB.py")
    suts.append(tmpdir / "sutC.txt")

    for index in range(0, len(suts)):
        suts[index].write(
            "from ltp.sut import SUT\n\n"
            f"class SUT{index}(SUT):\n"
            "    @property\n"
            "    def name(self) -> str:\n"
            f"        return 'mysut{index}'\n"
        )

    ltp.main._discover_sut(str(tmpdir))

    assert len(ltp.main.LOADED_SUT) == 2

    for index in range(0, len(ltp.main.LOADED_SUT)):
        assert ltp.main.LOADED_SUT[index].name == f"mysut{index}"
