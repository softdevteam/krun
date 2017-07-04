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

from collections import OrderedDict


class Audit(object):
    def __init__(self, audit_dict):
        assert isinstance(audit_dict, dict)
        self._audit = audit_dict
        for key, value in audit_dict.iteritems():
            if type(value) is str:
                audit_dict[key] = value.decode("utf-8")

    def __contains__(self, key):
        return key in self._audit

    def __getitem__(self, key):
        return self._audit[key]

    def __setitem__(self, key, value):
        self._audit[key] = value

    def __unicode__(self):
        s = ""
        # important that the sections are sorted, for diffing
        for key, text in OrderedDict(sorted(self._audit.iteritems())).iteritems():
            s += "Audit Section: %s" % key + "\n"
            s += "#" * 78 + "\n\n"
            s += unicode(text) + "\n\n"
        return s

    def __len__(self):
        return len(self._audit)

    @property
    def audit(self):
        return self._audit

    @audit.setter
    def audit(self, audit_dict):
        self._audit = audit_dict

    def __ne__(self, other):
        return not self == other

    def __eq__(self, other):
        if ((not isinstance(other, self.__class__)) or
                (not len(self) == len(other))):
            return False
            if "uname" in other:
                return self["uname"] == other["uname"]
        return True
