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
    assert "Environment bach is already defined" in caplog.text


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
