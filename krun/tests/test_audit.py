# Copyright (c) 2017 King's College London
# created by the Software Development Team <http://soft-dev.org/>
#
# The Universal Permissive License (UPL), Version 1.0
#
# Subject to the condition set forth below, permission is hereby granted to any
# person obtaining a copy of this software, associated documentation and/or
# data (collectively the "Software"), free of charge and under any and all
# copyright rights in the Software, and any and all patent rights owned or
# freely licensable by each licensor hereunder covering either (i) the
# unmodified Software as contributed to or provided by such licensor, or (ii)
# the Larger Works (as defined below), to deal in both
#
# (a) the Software, and
# (b) any piece of software and/or hardware listed in the lrgrwrks.txt file if
# one is included with the Software (each a "Larger Work" to which the Software
# is contributed by such licensors),
#
# without restriction, including without limitation the rights to copy, create
# derivative works of, display, perform, and distribute the Software and make,
# use, sell, offer for sale, import, export, have made, and have sold the
# Software and the Larger Work(s), and to sublicense the foregoing rights on
# either these or other terms.
#
# This license is subject to the following condition: The above copyright
# notice and either this complete permission notice or at a minimum a reference
# to the UPL must be included in all copies or substantial portions of the
# Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

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
