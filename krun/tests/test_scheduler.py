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
from krun.config import Config
from krun.scheduler import (mean, ExecutionJob, ExecutionScheduler,
                            ManifestManager)
from krun.tests import BaseKrunTest
from krun.results import Results
import krun.util

import os
import pytest
import krun.util as util
import re
from krun.tests import TEST_DIR
from krun.tests.test_results import no_results_instantiation_check


class _TestReboot(Exception):
    pass

def type_check_results(results):
    for k, execs in results.wallclock_times.iteritems():
        assert type(execs) is list
        for one_exec in execs:
            assert type(one_exec) is list
            assert all([type(x) is float for x in one_exec])

    for k, execs in results.eta_estimates.iteritems():
        assert type(execs) is list
        assert all([type(x) is float for x in execs])

    assert type(results.audit) is type(Audit(dict()))
    assert type(results.config) is type(Config())
    assert type(results.error_flag) is bool


def make_reboot_raise(monkeypatch):
    def dummy_do_reboot(self):
        from logging import info
        info("SIMULATED: reboot via exception")
        raise _TestReboot()
    monkeypatch.setattr(util, '_do_reboot', dummy_do_reboot)


def no_envlogs(monkeypatch):
    def dummy_stash_envlog(tmp_filename, config, platform, key, exec_num):
        pass
    monkeypatch.setattr(util, 'stash_envlog', dummy_stash_envlog)


def emulate_first_reboot(platform, config, monkeypatch):
    no_results_instantiation_check(monkeypatch)

    platform.starting_temperatures = platform.take_temperature_readings()
    manifest = ManifestManager(config, platform, new_file=True)
    manifest.set_starting_temperatures(platform.starting_temperatures)
    results = Results(config, platform)
    results.write_to_file()
    return manifest

def run_with_captured_reboots(config, platform, monkeypatch):
    """Runs a session to completion using exceptions to capture reboots

    Returns the number of reboots and the last scheduler"""

    no_envlogs(monkeypatch)
    make_reboot_raise(monkeypatch)
    krun.util.assign_platform(config, platform)
    reboots = 0

    manifest = emulate_first_reboot(platform, config, monkeypatch)
    if manifest.num_execs_left == 0:
        sched = ExecutionScheduler(config, platform.mailer, platform,
                                   dry_run=True)
        return reboots, sched
    reboots += 1

    # Run the main benchmarking loop
    while True:
        sched = ExecutionScheduler(config, platform.mailer, platform, dry_run=True)
        try:
            sched.run()
        except _TestReboot:
            reboots += 1
        else:
            # normal exit() from run -- schedule finished
            break

    return reboots, sched


class TestScheduler(BaseKrunTest):
    """Test the job scheduler."""

    def test_mean_empty(self):
        with pytest.raises(ValueError):
            assert mean([]) == .0

    def test_mean(self):
        flts = [1.0 / n for n in range(1, 11)]
        assert mean(flts) * float(len(flts)) == sum(flts)
        flts = [n / 10.0 for n in range(11)]
        assert mean(flts) * float(len(flts)) == sum(flts)

    def test_run_schedule0001(self, monkeypatch, mock_platform):
        config = Config(os.path.join(TEST_DIR, "one_exec.krun"))
        n_reboots, sched = run_with_captured_reboots(config, mock_platform,
                                                     monkeypatch)
        assert sched.manifest.total_num_execs == 1
        assert sched.manifest.num_execs_left == 0
        assert n_reboots == 1

        results = Results(config, mock_platform,
                          results_file=config.results_filename())
        type_check_results(results)

        assert len(results.wallclock_times) == 1  # 1 benchmark, 1 vm
        for key, execs in results.wallclock_times.iteritems():
            assert len(execs) == 1
            for _exec in execs:
                assert len(_exec) == 0  # due to dry run

        os.unlink(config.results_filename())
        os.unlink(sched.manifest.path)

    def test_run_schedule0002(self, mock_platform, monkeypatch):
        config = Config(os.path.join(TEST_DIR, "example.krun"))
        n_reboots, sched = run_with_captured_reboots(config, mock_platform,
                                                     monkeypatch)
        assert n_reboots == 8  # 2 benchmarks, 2 vms, 2 execs

        results = Results(config, mock_platform,
                          results_file=config.results_filename())
        type_check_results(results)

        assert len(results.wallclock_times) == 4  # 2 benchmarks, 2 vms
        for key, execs in results.wallclock_times.iteritems():
            assert len(execs) == 2
            for _exec in execs:
               assert len(_exec) == 0  # due to dry run

        os.unlink(config.results_filename())
        os.unlink(sched.manifest.path)

    def test_run_schedule0003(self, mock_platform, monkeypatch):
        config = Config(os.path.join(TEST_DIR, "example_all_skip.krun"))
        n_reboots, sched = run_with_captured_reboots(config, mock_platform,
                                                     monkeypatch)
        assert n_reboots == 0 # all skipped!
        os.unlink(sched.manifest.path)
        os.unlink(config.results_filename())

    def test_run_schedule0004(self, mock_platform, monkeypatch):
        config = Config(os.path.join(TEST_DIR, "example_skip_1vm.krun"))
        n_reboots, sched = run_with_captured_reboots(config, mock_platform,
                                                     monkeypatch)
        assert n_reboots == 4  # 2 benchmarks, 2 vms, 2 execs, one VM skipped

        results = Results(config, mock_platform,
                          results_file=config.results_filename())
        type_check_results(results)

        assert len(results.wallclock_times) == 4  # 2 benchmarks, 2 vms
        for key, execs in results.wallclock_times.iteritems():
            if "CPython" in key:
                assert len(execs) == 0
            else:
                assert len(execs) == 2

            for _exec in execs:
                assert len(_exec) == 0  # due to dry run

        os.unlink(config.results_filename())
        os.unlink(sched.manifest.path)

    def test_run_schedule0005(self, mock_platform, monkeypatch):

        def dummy_execjob_run(self, mailer, dryrun=False):
            return self.empty_measurements, {}, "E"  # pretend jobs fail
        monkeypatch.setattr(ExecutionJob, 'run', dummy_execjob_run)

        config = Config(os.path.join(TEST_DIR, "example.krun"))
        n_reboots, sched = run_with_captured_reboots(config, mock_platform,
                                                     monkeypatch)
        assert n_reboots == 8  # 2 benchmarks, 2 vms, 2 execs

        results = Results(config, mock_platform,
                          results_file=config.results_filename())
        type_check_results(results)

        assert len(results.wallclock_times) == 4  # 2 benchmarks, 2 vms
        for key, execs in results.wallclock_times.iteritems():
            assert len(execs) == 2

            for _exec in execs:
                assert len(_exec) == 0  # due to error

        os.unlink(config.results_filename())
        os.unlink(sched.manifest.path)

    def test_num_emails_sent_persists0001(self, monkeypatch, mock_platform):
        make_reboot_raise(monkeypatch)
        no_envlogs(monkeypatch)

        config = Config(os.path.join(TEST_DIR, "example.krun"))
        krun.util.assign_platform(config, mock_platform)
        emulate_first_reboot(mock_platform, config, monkeypatch)
        sched = ExecutionScheduler(config, mock_platform.mailer, mock_platform,
                                   dry_run=True)
        sched.mailer.recipients = ["noone@localhost"]

        assert sched.manifest.num_mails_sent == 0
        sched.mailer.send("subject", "body", manifest=sched.manifest)
        assert sched.manifest.num_mails_sent == 1
        try:
            sched.run()
        except _TestReboot:
            pass
        else:
            assert False

        # suppose a reboot happened now
        del sched
        del config
        config = Config(os.path.join(TEST_DIR, "example.krun"))
        krun.util.assign_platform(config, mock_platform)
        sched = ExecutionScheduler(config, mock_platform.mailer, mock_platform,
                                   dry_run=True)
        assert sched.manifest.num_mails_sent == 1
        os.unlink(sched.manifest.path)

    def test_error_flag_persists0001(self, monkeypatch, mock_platform):
        """Check a failing exec will correctly set the error flag"""

        make_reboot_raise(monkeypatch)
        no_envlogs(monkeypatch)

        # pretend exec fails
        def dummy_job_run(self, mailer, dry):
            measurements = self.make_empty_measurement()
            return measurements, None, 'E'  # measurements, instr_data, flag
        monkeypatch.setattr(ExecutionJob, 'run', dummy_job_run)

        config = Config(os.path.join(TEST_DIR, "example.krun"))
        krun.util.assign_platform(config, mock_platform)
        emulate_first_reboot(mock_platform, config, monkeypatch)
        results_path = config.results_filename()

        # To start, the error flag is not set
        results = Results(config, mock_platform, results_file=results_path)
        assert not results.error_flag

        # run a (failing) execution, which will dump the results file
        sched = ExecutionScheduler(config, mock_platform.mailer, mock_platform,
                                   dry_run=True)
        try:
            sched.run()
        except _TestReboot:
            pass
        else:
            assert False

        # reload results and check the error flag is now set
        results = Results(config, mock_platform, results_file=results_path)
        assert results.error_flag

        os.unlink(sched.manifest.path)
        os.unlink(results_path)

    def test_error_flag_persists0002(self, monkeypatch, mock_platform):
        """Check a changed dmesg will correctly set the error flag"""

        make_reboot_raise(monkeypatch)
        no_envlogs(monkeypatch)

        # pretend dmesg changes
        def dummy_check_for_dmesg_changes(self):
            return True
        monkeypatch.setattr(mock_platform, 'check_dmesg_for_changes',
                            dummy_check_for_dmesg_changes)

        config = Config(os.path.join(TEST_DIR, "example.krun"))
        krun.util.assign_platform(config, mock_platform)
        emulate_first_reboot(mock_platform, config, monkeypatch)
        results_path = config.results_filename()

        # To start, the error flag is not set
        results = Results(config, mock_platform, results_file=results_path)
        assert not results.error_flag

        # run an execution where the dmesg changes
        sched = ExecutionScheduler(config, mock_platform.mailer, mock_platform,
                                   dry_run=True)
        try:
            sched.run()
        except _TestReboot:
            pass
        else:
            assert False

        # reload results and check the error flag is now set
        results = Results(config, mock_platform, results_file=results_path)
        assert results.error_flag

        os.unlink(sched.manifest.path)
        os.unlink(results_path)

    def test_pre_and_post_exec_cmds0001(self, monkeypatch, mock_platform):
        cap_cmds = []
        def dummy_run_shell_cmd(cmd, failure_fatal=False, extra_env=None):
            cap_cmds.append(cmd)
            return "", "", 0

        monkeypatch.setattr(krun.util, "run_shell_cmd", dummy_run_shell_cmd)

        config = Config(os.path.join(TEST_DIR, "one_exec.krun"))
        config.PRE_EXECUTION_CMDS = ["cmd1", "cmd2"]
        config.POST_EXECUTION_CMDS = ["cmd3", "cmd4"]

        n_reboots, sched = run_with_captured_reboots(config, mock_platform,
                                                     monkeypatch)
        os.unlink(config.results_filename())
        os.unlink(sched.manifest.path)

        assert n_reboots == 1
        expect = ["cmd1", "cmd2", "cmd3", "cmd4"]
        assert cap_cmds == expect

    def test_pre_and_post_exec_cmds0002(self, monkeypatch, mock_platform):
        config = Config(os.path.join(TEST_DIR, "one_exec.krun"))
        path = os.path.join(TEST_DIR, "shell-out")
        cmd = "echo ${KRUN_RESULTS_FILE}:${KRUN_LOG_FILE}:${KRUN_MANIFEST_FILE} > %s" % path
        config.POST_EXECUTION_CMDS = [cmd]

        krun.util.assign_platform(config, mock_platform)
        n_reboots, sched = run_with_captured_reboots(config, mock_platform,
                                                     monkeypatch)
        os.unlink(config.results_filename())

        with open(path) as fh:
            got = fh.read().strip()

        os.unlink(path)
        os.unlink(sched.manifest.path)

        assert n_reboots == 1
        elems = got.split(":")
        assert os.path.basename(elems[0]) == "one_exec_results.json.bz2"
        assert os.path.basename(elems[1]) == "one_exec.log"
        assert os.path.basename(elems[2]) == "one_exec.manifest"

        # all paths should be in the same dir
        dirnames = [os.path.dirname(x) for x in elems]
        assert dirnames[0] == dirnames[1] == dirnames[2]

    def test_pre_and_post_cmds0003(self, monkeypatch, mock_platform):
        """Check that the pre/post commands use a shell and don't just exec(3)"""

        config = Config(os.path.join(TEST_DIR, "one_exec.krun"))
        tmp_file = os.path.join(TEST_DIR, "prepost.txt")

        # commands use shell syntax
        config.PRE_EXECUTION_CMDS = ["echo 'pre' > %s" % tmp_file]
        config.POST_EXECUTION_CMDS = ["echo 'post' >> %s" % tmp_file]

        n_reboots, sched = run_with_captured_reboots(config, mock_platform,
                                                     monkeypatch)
        assert n_reboots == 1
        os.unlink(config.results_filename())
        os.unlink(sched.manifest.path)

        with open(tmp_file) as fh:
            got = fh.read()

        os.unlink(tmp_file)
        assert got == "pre\npost\n"

    def test_boot_loop0001(self, monkeypatch, mock_platform, caplog):
        make_reboot_raise(monkeypatch)
        no_envlogs(monkeypatch)

        config = Config(os.path.join(TEST_DIR, "example.krun"))
        krun.util.assign_platform(config, mock_platform)

        emulate_first_reboot(mock_platform, config, monkeypatch)

        # Simulate a boot loop
        sched = ExecutionScheduler(config, mock_platform.mailer, mock_platform,
                                   dry_run=True)
        sched.manifest.num_reboots = 9998  # way too many
        sched.manifest.update_num_reboots() # increments and writes out file

        with pytest.raises(krun.util.FatalKrunError):
            sched.run()

        expect = ("HALTING now to prevent an infinite reboot loop: "
                  "INVARIANT num_reboots <= num_jobs violated. Krun was about "
                  "to execute reboot number: 10000. 1 jobs have been "
                  "completed, 7 are left to go.")
        assert expect in caplog.text()

        os.unlink(config.results_filename())
        os.unlink(sched.manifest.path)

    def test_audit_differs0001(self, monkeypatch, mock_platform, caplog):
        """Check that if the audit differs, a crash occurs"""

        make_reboot_raise(monkeypatch)
        no_envlogs(monkeypatch)

        config = Config(os.path.join(TEST_DIR, "example.krun"))
        krun.util.assign_platform(config, mock_platform)
        emulate_first_reboot(mock_platform, config, monkeypatch)
        results_path = config.results_filename()

        # mutate the audit, so it won't match later
        results = Results(config, mock_platform, results_file=results_path)
        results.audit._audit["wibble"] = "wut"
        results.write_to_file()

        sched = ExecutionScheduler(config, mock_platform.mailer, mock_platform,
                                   dry_run=True)
        with pytest.raises(krun.util.FatalKrunError):
            sched.run()

        expect = "This is only valid if the machine you are using is identical"
        assert expect in caplog.text()

        os.unlink(sched.manifest.path)
        os.unlink(results_path)
