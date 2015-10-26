"""
Dummy benchmark.
Each iteration sleeps for one second.
"""

import time

DELAY = 1  # second

def dummy():
    """The benchmark itself.
    """
    time.sleep(DELAY)

def run_iter(n):
    """Entry point to the benchmark.
    This method is called by krun and runs one iteration of the benchmark.
    """
    dummy()
