from krun.time_estimate import TimeEstimateFormatter, now_str
from krun.results import Results
from krun import util

from logging import warn, info, error, debug

import os, subprocess, sys, time

# Wait this many seconds for the init system to finish bringing up services.
STARTUP_WAIT_SECONDS = 2 * 60

EMPTY_MEASUREMENTS = {
    "wallclock_times": [],
    "core_cycle_counts": [],
    "aperf_counts": [],
    "mperf_counts": [],
}

def mean(seq):
    if len(seq) == 0:
        raise ValueError("Cannot calculate mean of empty sequence.")
    return sum(seq) / float(len(seq))


class JobMissingError(Exception):
    """This is exception is called by the scheduler, in resume mode.
    This exception should be raised when  the user has asked to
    resume an interrupted benchmark, and the json results contain
    an execution that does not appear in the config file.
    """
    def __init__(self, key):
        self.key = key


class ScheduleEmpty(Exception):
    pass


class ManifestManager(object):
    """Data structure for working with the manifest file"""

    PATH = "krun.manifest"

    def __init__(self):
        """Constructor reads an existing manifest file"""

        self._parse()

    def _reset(self):
        # All populated in _parse()
        self.next_exec_key = None
        self.next_exec_idx = -1
        self.next_exec_flag_offset = None
        self.num_execs_left = 0
        self.total_num_execs = 0
        self.eta_avail_idx = 0
        self.outstanding_exec_counts = {}

    def _open(self):
        path = os.path.abspath(ManifestManager.PATH)
        debug("Reading status cookie from %s" % path)
        return open(path, "r+")

    def _parse(self):
        self._reset()
        fh = self._open()
        offset = 0

        # Parse manifest header
        for line in fh:
            offset += len(line)
            line = line.strip()
            if line == "keys":
                break
            else:
                key, val = line.split("=")
                if key == "eta_avail_idx":
                    self.eta_avail_idx = int(val)
                else:
                    assert False
        else:
            assert False

        # Get info from the rest of the file
        exec_idx = 0
        for line in fh:
            flag, key = line.strip().split(" ")
            if key not in self.outstanding_exec_counts:
                self.outstanding_exec_counts[key] = 0

            if flag in ["S", "E", "C"]:  # skip, error, completed
                pass
            elif flag == "O":  # outstanding
                self.outstanding_exec_counts[key] += 1
                if self.num_execs_left == 0:  # first outstanding exec
                    self.next_exec_key = key
                    self.next_exec_flag_offset = offset
                    self.next_exec_idx = exec_idx
                self.num_execs_left += 1
            else:
                assert False  # bogus flag

            exec_idx += 1
            offset += len(line)
        fh.close()
        self.total_num_execs = exec_idx

    def update(self, flag):
        """Updates the manifest flag for the just-ran execution

        This should only be called once per instance, as krun is expected to
        reboot (or fake reboot) between executions."""

        debug("Update manifest flag: %s" % flag)
        fh = self._open()
        fh.seek(self.next_exec_flag_offset)
        fh.write(flag)
        fh.close()

        self._reset()
        self._parse()  # update stats

    @classmethod
    def from_config(cls, config):
        """Makes the inital manifest file from the config

        Returns two sets: non_skipped_keys, skipped_keys"""

        skipped_keys, non_skipped_keys = set(), set()
        manifest = []

        one_exec_scheduled = False
        eta_avail_idx = -1
        for exec_n in xrange(config.N_EXECUTIONS):
            for vm_name, vm_info in config.VMS.items():
                for bmark, param in config.BENCHMARKS.items():
                    for variant in vm_info["variants"]:
                        key = "%s:%s:%s" % (bmark, vm_name, variant)
                        if not config.should_skip(key):
                            non_skipped_keys |= set([key])
                            manifest.append("O " + key)
                            if one_exec_scheduled and eta_avail_idx == -1:
                                # first job of second executions eta becomes known.
                                eta_avail_idx = len(manifest) - 1
                        else:
                            skipped_keys |= set([key])
                            manifest.append("S " + key)
                            if not one_exec_scheduled:
                                debug("%s is in skip list. Not scheduling." %
                                      key)
            one_exec_scheduled = True

        path = os.path.abspath(ManifestManager.PATH)
        debug("Writing manifest to %s" % path)

        with open(path, "w") as fh:
            fh.write("eta_avail_idx=%s\n" % eta_avail_idx)
            fh.write("keys\n")
            for item in manifest:
                fh.write("%s\n" % item)

        return cls()


class ExecutionJob(object):
    """Represents a single executions level benchmark run"""

    def __init__(self, sched, vm_name, vm_info, benchmark, variant, parameter):
        self.sched = sched
        self.vm_name, self.vm_info = vm_name, vm_info
        self.benchmark = benchmark
        self.variant = variant
        self.parameter = parameter

        # Used in results JSON and ETA dict
        self.key = "%s:%s:%s" % (self.benchmark, self.vm_name, self.variant)

    def __str__(self):
        return self.key

    __repr__ = __str__

    def __eq__(self, other):
        return (self.sched == other.sched and
                self.key == other.key and
                self.parameter == other.parameter)

    def add_exec_time(self, exec_time):
        """Feed back a rough execution time for ETA usage"""
        self.sched.add_eta_info(self.key, exec_time)

    def run(self, mailer, dry_run=False):
        """Runs this job (execution)"""

        flag = None

        entry_point = self.sched.config.VARIANTS[self.variant]
        vm_def = self.vm_info["vm_def"]
        vm_def.dry_run = dry_run

        # Set heap limit
        heap_limit_kb = self.sched.config.HEAP_LIMIT
        stack_limit_kb = self.sched.config.STACK_LIMIT
        in_proc_iters = self.vm_info["n_iterations"]

        stdout, stderr, rc = vm_def.run_exec(
            entry_point, self.benchmark, in_proc_iters,
            self.parameter, heap_limit_kb, stack_limit_kb)

        if not dry_run:
            try:
                measurements = util.check_and_parse_execution_results(
                    stdout, stderr, rc)
                flag = "C"
            except util.ExecutionFailed as e:
                util.log_and_mail(mailer, error, "Benchmark failure: %s" % self.key, e.message)
                measurements = EMPTY_MEASUREMENTS
                flag = "E"

            if vm_def.instrument:
                instr_data = vm_def.get_instr_data()
                for k, v in instr_data.iteritems():
                    assert len(instr_data[k]) == in_proc_iters
            else:
                instr_data = {}
        else:
            measurements = EMPTY_MEASUREMENTS
            instr_data = {}
            flag = "C"

        # We print the status *after* benchmarking, so that I/O cannot be
        # committed during benchmarking. In production, we will be rebooting
        # before the next execution, so we are grand.
        info("Finished '%s(%d)' (%s variant) under '%s'" %
                    (self.benchmark, self.parameter, self.variant, self.vm_name))

        assert flag is not None
        return measurements, instr_data, flag


class ExecutionScheduler(object):
    """Represents our entire benchmarking session"""

    def __init__(self, config, mailer, platform,
                 resume=False, reboot=False, dry_run=False,
                 started_by_init=False):
        self.mailer = mailer

        self.config = config
        self.eta_avail = 0
        self.platform = platform
        self.resume = resume
        self.reboot = reboot
        self.dry_run = dry_run
        self.started_by_init = started_by_init

        self.log_path = self.config.log_filename(self.resume)

        if not self.resume:
            self.manifest = ManifestManager.from_config(config)
            self.results = Results(self.config, self.platform)
            self.results.write_to_file()  # scaffold results file
        else:
            self.manifest = ManifestManager()
            self.results = None

    def get_estimated_exec_duration(self, key):
        previous_exec_times = self.results.eta_estimates.get(key)
        if previous_exec_times:
            return mean(previous_exec_times)
        else:
            return None # we don't know

    def get_estimated_overall_duration(self):
        secs = 0
        for key, num_execs in self.manifest.outstanding_exec_counts.iteritems():
            per_exec = self.get_estimated_exec_duration(key)
            if per_exec is not None:
                secs += self.get_estimated_exec_duration(key) * num_execs
            else:
                return None  # unknown time
        return secs

    def get_exec_estimate_time_formatter(self, key):
        return TimeEstimateFormatter(self.get_estimated_exec_duration(key))

    def get_overall_time_estimate_formatter(self):
        return TimeEstimateFormatter(self.get_estimated_overall_duration())

    def add_eta_info(self, key, exec_time):
        self.results.eta_estimates[key].append(exec_time)

    def _make_pre_post_cmd_env(self):
        """Prepare an environment dict for pre/post execution hooks"""

        jobs_until_eta_known = self.manifest.eta_avail_idx - \
            self.manifest.next_exec_idx
        if jobs_until_eta_known > 0:
            eta_val = "Unknown. Known in %d process executions." % \
                jobs_until_eta_known
        else:
            eta_val = self.get_overall_time_estimate_formatter().finish_str

        return {
            "KRUN_RESULTS_FILE": self.config.results_filename(),
            "KRUN_LOG_FILE": self.config.log_filename(resume=True),
            "KRUN_ETA_DATUM": now_str(),
            "KRUN_ETA_VALUE": eta_val,
        }

    def run(self):
        """Benchmark execution starts here"""

        if not self.started_by_init:
            util.log_and_mail(self.mailer, debug,
                              "Benchmarking started",
                              "Benchmarking started.\nLogging to %s" %
                              self.log_path,
                              bypass_limiter=True)

        # Important that the dmesg is collected after the above startup wait.
        # Otherwise we get spurious dmesg changes.
        self.platform.collect_starting_dmesg()

        while True:
            self.platform.wait_for_temperature_sensors()

            if self.reboot and not self.resume:
                info("Reboot prior to first execution")
                self._reboot(self.manifest.total_num_execs)

            # If we get here, this is a real run, with a benchmark about to
            # run. Results should never be in memory at this point (as they
            # grow over time, and can get very large, thus potentially
            # influencing the benchmark)
            assert self.results is None

            bench, vm, variant = self.manifest.next_exec_key.split(":")
            job = ExecutionJob(self, vm, self.config.VMS[vm], bench, variant,
                               self.config.BENCHMARKS[bench])

            # Run the user's pre-process-execution commands We can't put an ETA
            # estimate in the evironment for the pre-commands as we have not
            # (and should not) load the results file into memory yet.
            util.run_shell_cmd_list(
                self.config.PRE_EXECUTION_CMDS,
            )

            # We collect rough execution times separate from real results. The
            # reason for this is that, even if a benchmark crashes it takes
            # time and we need to account for this when making estimates. A
            # crashing benchmark will give an empty list of iteration times,
            # meaning we can't use 'raw_exec_result' below for estimates.
            exec_start_time = time.time()
            measurements, instr_data, flag = job.run(self.mailer, self.dry_run)
            exec_end_time = time.time()

            if flag == "E":
                self.results.error_flag = True

            # Store results
            self.results = Results(self.config, self.platform,
                                   results_file=self.config.results_filename())
            self.results.append_exec_measurements(job.key, measurements)
            self.results.add_instr_data(job.key, instr_data)

            eta_info = exec_end_time - exec_start_time
            if self.reboot and not self.platform.fake_reboots:
                # Add time taken to wait for system to come up if we are in
                # reboot mode.
                eta_info += STARTUP_WAIT_SECONDS
            self.add_eta_info(job.key, eta_info)

            # We dump the json after each process exec so we can monitor the
            # JSON file mid-run. It is overwritten each time.
            self.results.write_to_file()
            self.manifest.update(flag)

            # Run the user's post-process-execution commands with updated
            # ETA estimates. Important that this happens *after* dumping
            # results, as the user is likely copying intermediate results to
            # another host.
            util.run_shell_cmd_list(
                self.config.POST_EXECUTION_CMDS,
                extra_env=self._make_pre_post_cmd_env()
            )

            tfmt = self.get_overall_time_estimate_formatter()

            if self.manifest.eta_avail_idx == self.manifest.next_exec_idx:
                # We just found out roughly how long the session has left, mail out.
                msg = "ETA for current session now known: %s" % tfmt.finish_str
                util.log_and_mail(self.mailer, debug,
                             "ETA for Current Session Available",
                             msg, bypass_limiter=True)

            info("{:<25s}: {} ({} from now)".format(
                "Estimated completion (whole session)", tfmt.finish_str,
                tfmt.delta_str))

            info("%d executions left in scheduler queue" % self.manifest.num_execs_left)

            if self.manifest.num_execs_left > 0 and \
                    self.manifest.eta_avail_idx > self.manifest.next_exec_idx:
                info("Executions until ETA known: %s" %
                     (self.manifest.eta_avail_idx -
                      self.manifest.next_exec_idx))

            if self.platform.check_dmesg_for_changes():
                self.results.error_flag = True

            if self.manifest.num_execs_left > 0:
                # print info about the next job
                benchmark, vm_name, variant = \
                    self.manifest.next_exec_key.split(":")
                info("Next execution is '%s(%d)' (%s variant) under '%s'" %
                     (benchmark, self.config.BENCHMARKS[benchmark], variant, vm_name))

                tfmt = self.get_exec_estimate_time_formatter(job.key)
                info("{:<35s}: {} ({} from now)".format(
                    "Estimated completion (next execution)",
                    tfmt.finish_str,
                    tfmt.delta_str))
            elif self.manifest.num_execs_left == 0:
                break  # done
            else:
                assert False

            if self.reboot and self.manifest.num_execs_left > 0:
                info("Reboot in preparation for next execution")
                self._reboot(self.manifest.total_num_execs)

        self.platform.save_power()

        info("Done: Results dumped to %s" % self.config.results_filename())
        err_msg = "Errors/warnings occurred -- read the log!"
        if self.results.error_flag:
            warn(err_msg)

        msg = "Session completed. Log file at: '%s'" % (self.log_path)

        if self.results.error_flag:
            msg += "\n\n%s" % err_msg

        if self.reboot:
            msg += "\n\nDon't forget to disable Krun at boot."

        util.log_and_mail(self.mailer, info, "Benchmarks Complete", msg,
                          bypass_limiter=True)

    def _reboot(self, expected_reboots):
        self.results.reboots += 1
        debug("About to execute reboot: %g, expecting %g in total." %
              (self.results.reboots, expected_reboots))
        # Dump the results file. This may already have been done, but we
        # have changed self.nreboots, which needs to be written out.
        # XXX can we prevent writing the results file twice? It is slow for big data.
        self.results.write_to_file()

        if self.results.reboots > expected_reboots:
            assert False # XXX unbreak
            util.fatal(("HALTING now to prevent an infinite reboot loop: " +
                        "INVARIANT num_reboots <= num_jobs violated. " +
                        "Krun was about to execute reboot number: %g. " +
                        "%g jobs have been completed, %g are left to go.") %
                       (self.results.reboots, self.jobs_done, len(self)))
        if self.platform.fake_reboots:
            warn("SIMULATED: reboot (--fake-reboots)")
            args =  sys.argv
            if not self.started_by_init:
                args.extend(["--resume", "--started-by-init"])
            debug("Simulated reboot with args: " + " ".join(args))
            os.execv(args[0], args)  # replace myself
            assert False  # unreachable
        else:
            subprocess.call(self.platform.get_reboot_cmd())
