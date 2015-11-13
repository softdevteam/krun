from krun import EntryPoint


def test_eq():
    ep0 = EntryPoint("test0", subdir="/root/")
    ep1 = EntryPoint("test1", subdir="/home/krun/")
    assert ep0 == ep0
    assert ep1 == ep1
    assert not ep0 == ep1
    assert not ep0 == list()
