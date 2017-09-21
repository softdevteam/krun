#!/usr/bin/env python2.7
"""Check the environment logs of many pexecs for similarity.

Usage: check_envlogs.py <envlog dir>

We check:
 * The SHA1 hashes of the envlogs.
 * The sizes of the envlogs.

When hashing, we ignore `SUDO_COMMAND=` lines, since this contains a variable
(but fixed-length) wrapper filename.

The script prints nothing if all is well. If the script prints anything, then
non-unique filesizes or hashes have been detected. If this is the case, the
benchmarking environment deviated between runs (which is bad).
"""

import os
import sys
import hashlib
import pprint
import stat
from collections import defaultdict


def hash_file(filename):
    """Hash a file and return a hex string"""

    hasher = hashlib.sha1()
    with open(filename, 'rb') as fh:
        for line in fh:
            if line.startswith("SUDO_COMMAND="):
                continue  # the dash wrapper filename varies, we allow this
            hasher.update(line)
    return hasher.hexdigest()


def get_key_dct(files):
    """From a list of files in an envlog directory, build a dict mapping a
    benchmark key to filenames"""

    key_dct = {}
    for fl in files:
        elems = fl.split("__")
        key = "{}:{}:{}".format(*elems[:-1])
        if key not in key_dct:
            key_dct[key] = []
        key_dct[key].append(fl)
    return key_dct


def get_filesize(filename):
    """Get the size of a file in bytes"""

    mode = os.stat(filename)
    return mode[stat.ST_SIZE]


def print_problems(dct):
    for key, vals in dct.iteritems():
        print("    %s:" % key)
        for idx, val in enumerate(vals):
            if idx == 4:
                print("        ... (%d more)" % (len(vals) - 4, ))
                break
            print("        %s" % val)
    print("")


def check(dirname, key, files):
    """Check the envlogs for the given benchmark key"""

    hashes = defaultdict(set)
    sizes = defaultdict(set)
    for fl in files:
        path = os.path.join(dirname, fl)

        # Hash
        hash = hash_file(path)
        hashes[hash].add(fl)

        # Size
        size = get_filesize(path)
        sizes[size].add(fl)

    num_hashes = len(hashes)
    if num_hashes > 1:
        print("%s: %d unique hashes:" % (key, num_hashes))
        print_problems(hashes)

    num_sizes = len(sizes)
    if num_sizes > 1:
        print("%s: %d unique file sizes:" % (key, num_sizes))
        print_problems(sizes)


def main(dirname):
    files = os.listdir(dirname)
    key_dct = get_key_dct(files)
    for key, files in key_dct.iteritems():
        check(dirname, key, files)


if __name__ == "__main__":
    try:
        dirname = sys.argv[1]
    except IndexError:
        print(__doc__)
        sys.exit(1)
    main(dirname)
