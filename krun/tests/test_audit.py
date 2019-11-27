from krun.audit import Audit


def test_eq():
    audit = Audit({"a": 100, "b": 200})
    empty = Audit(dict())
    assert audit == audit
    assert empty == empty
    assert not empty == audit
    assert not list() == audit
    a0 = {"uname": "Linux"}
    a1 = {"uname": "BSD"}
    assert not a0 == a1
    assert a0 == a0
    assert a1 == a1


def test_get_set_item():
    audit = Audit({"a": 100, "b": 200})
    empty = Audit(dict())
    assert  audit["a"] == 100
    assert  audit["b"] == 200
    empty["a"] = 100
    empty["b"] = 200
    assert audit == empty


def test_contains():
    audit = Audit({"a": 100, "b": 200})
    assert "a" in audit
    assert not "c" in audit


def test_property():
    audit = Audit({"a": 100, "b": 200})
    assert audit.audit == {"a": 100, "b": 200}
    empty = Audit(dict())
    empty.audit = {"a": 100, "b": 200}
    assert empty == audit


def test_unicode():
    audit = Audit({"a": 100, "b": 200})
    spacer = "#" * 78
    expected = "Audit Section: a\n"
    expected += spacer + u"\n\n"
    expected += "100\n\n"
    expected += "Audit Section: b\n"
    expected += spacer + "\n\n"
    expected += "200\n\n"
    assert unicode(expected) == unicode(audit)
