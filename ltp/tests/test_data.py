"""
Unittests for data module.
"""
import pytest
import ltp.data


def test_read_runtest_error():
    """
    Test read_runtest method when raising errors.
    """
    with pytest.raises(ValueError):
        ltp.data.read_runtest("suite", None)

    with pytest.raises(ValueError):
        ltp.data.read_runtest("suite", "test01")


def test_read_runtest():
    """
    Test read_runtest method.
    """
    content = "# this is a test file\ntest01 test -f .\ntest02 test -d .\n"
    suite = ltp.data.read_runtest("suite", content)

    assert suite.name == "suite"
    assert suite.tests[0].name == "test01"
    assert suite.tests[0].command == "test"
    assert suite.tests[0].arguments == ['-f', '.']

    assert suite.tests[1].name == "test02"
    assert suite.tests[1].command == "test"
    assert suite.tests[1].arguments == ['-d', '.']
