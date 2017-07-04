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

# Tools to deal with setting and updating an environment dict.

from abc import ABCMeta, abstractmethod
from krun.util import fatal
import os


class EnvChange(object):
    __metaclass__ = ABCMeta

    def __init__(self, var, val):
        self.var, self.val = var, val

    @staticmethod
    def apply_all(changes, env):
        """Apply a collection of changes"""
        for change in changes:
            change.apply(env)

    @abstractmethod
    def apply(self, env):
        pass


class EnvChangeSet(EnvChange):
    def apply(self, env):
        cur_val = env.get(self.var, None)
        if cur_val is not None:
            fatal("Environment %s is already defined" % self.var)
        else:
            env[self.var] = self.val


class EnvChangeAppend(EnvChange):
    def apply(self, env):
        cur_val = env.get(self.var, None)
        if cur_val is None:
            env[self.var] = self.val
        else:
            env[self.var] = "%s%s%s" % (cur_val, os.pathsep, self.val)
