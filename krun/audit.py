from collections import OrderedDict
from logging import debug


class Audit(object):

    def __init__(self, audit_dict):
        assert isinstance(audit_dict, dict)
        self._audit = audit_dict

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

    def __eq__(self, other):
        if ((not isinstance(other, self.__class__)) or
            (not len(self) == len(other))):
            return False
        for key in self._audit:
            if key == "packages" and (key in self) and (key in other):
                continue
            if ((key not in other._audit) or (other[key] != self[key])):
                debug("%s keys differed in audit" % key)
                return False
        return True
