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
