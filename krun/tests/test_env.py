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

from krun.env import EnvChangeSet, EnvChangeAppend
from krun.util import FatalKrunError

import os
import pytest


def test_env_change_set(monkeypatch, caplog):
    env = EnvChangeSet("bach", 1685)
    assert env.var == "bach"
    assert env.val == 1685
    with pytest.raises(FatalKrunError):
        env.apply({"bach": 1695})
    assert "Environment bach is already defined" in caplog.text()


def test_env_change_set_apply():
    env = EnvChangeSet("bach", 1685)
    my_dict = {"handel": 1685}
    env.apply(my_dict)
    assert my_dict["bach"] == 1685
    assert my_dict["handel"] == 1685


def test_env_change_append():
    env = EnvChangeAppend("bach", 1685)
    assert env.var == "bach"
    assert env.val == 1685
    my_dict0 = {"handel": 1685}
    env.apply(my_dict0)
    assert my_dict0["bach"] == 1685
    assert my_dict0["handel"] == 1685
    my_dict1 = {"bach": 1750, "handel": 1759}
    env.apply(my_dict1)
    assert my_dict1["bach"] == "1750" + os.pathsep + "1685"
    assert my_dict1["handel"] == 1759


def test_env_apply_all():
    env0 = EnvChangeSet("bach", 1685)
    env1 = EnvChangeSet("handel", 1685)
    env2 = EnvChangeSet("vivaldi", 1678)
    assert env0.var == "bach"
    assert env0.val == 1685
    dict0 = {}
    dict1 = {"handel": 1685, "vivaldi": 1678, "bach": 1685}
    env0.apply_all((env0, env1, env2), dict0)
    assert dict0 == dict1
