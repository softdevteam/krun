from krun.time_estimate import TimeEstimateFormatter
from krun.results import Results
from krun import util

from collections import deque
from logging import warn, info, error, debug

import os, resource, subprocess, sys, time

# Wait this many seconds for the network to come up.
STARTUP_WAIT_SECONDS = 3 * 60


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

    def get_estimated_exec_duration(self):
        return self.sched.get_estimated_exec_duration(self.key)

    def get_exec_estimate_time_formatter(self):
        return self.sched.get_exec_estimate_time_formatter(self.key)

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

        entry_point = self.sched.config.VARIANTS[self.variant]
        vm_def = self.vm_info["vm_def"]
        vm_def.dry_run = dry_run

        info("Running '%s(%d)' (%s variant) under '%s'" %
                    (self.benchmark, self.parameter, self.variant, self.vm_name))

        # Print ETA for execution if available
        tfmt = self.get_exec_estimate_time_formatter()
        info("{:<35s}: {} ({} from now)".format(
                                         "Estimated completion (this exec)",
                                         tfmt.finish_str,
                                         tfmt.delta_str))

        # Set heap limit
        heap_limit_kb = self.sched.config.HEAP_LIMIT
        stack_limit_kb = self.sched.config.STACK_LIMIT

        stdout, stderr, rc = vm_def.run_exec(
            entry_point, self.benchmark, self.vm_info["n_iterations"],
            self.parameter, heap_limit_kb, stack_limit_kb)

        if not dry_run:
            try:
                iterations_results = util.check_and_parse_execution_results(stdout, stderr, rc)
            except util.ExecutionFailed as e:
                util.log_and_mail(mailer, error, "Benchmark failure: %s" % self.key, e.message)
                iterations_results = []
            return iterations_results

        else:
            return []


class ExecutionScheduler(object):
    """Represents our entire benchmarking session"""

    def __init__(self, config, mailer, platform,
                 resume=False, reboot=False, dry_run=False,
                 started_by_init=False):
        self.mailer = mailer

        self.config = config
        self.work_deque = deque()
        self.eta_avail = 0
        self.jobs_done = 0
        self.platform = platform
        self.resume = resume
        self.reboot = reboot
        self.dry_run = dry_run
        self.started_by_init = started_by_init

        if resume:
            self.results = Results(self.config, platform,
                                   results_file=self.config.results_filename())
        else:
            self.results = Results(self.config, platform)

        self.log_path = self.config.log_filename(self.resume)

    def set_eta_avail(self):
        """call after adding job before eta should become available"""
        self.eta_avail = len(self)

    def jobs_until_eta_known(self):
        return self.eta_avail - self.jobs_done

    def add_job(self, job):
        self.work_deque.append(job)

    def remove_job_by_key(self, key):
        for job in self.work_deque:
            if job.key == key:
                job_to_remove = job
                break
        else:
            raise JobMissingError(key)
        debug("Removed %s from schedule" % key)
        self.work_deque.remove(job_to_remove)

    def next_job(self):
        try:
            return self.work_deque.popleft()
        except IndexError:
            raise ScheduleEmpty() # we are done

    def __len__(self):
        return len(self.work_deque)

    def get_estimated_exec_duration(self, key):
        previous_exec_times = self.results.eta_estimates.get(key)
        if previous_exec_times:
            return mean(previous_exec_times)
        else:
            return None # we don't know

    def get_estimated_overall_duration(self):
        etas = [j.get_estimated_exec_duration() for j in self.work_deque]
        if None in etas:
            return None # we don't know
        return sum(etas)

    def get_exec_estimate_time_formatter(self, key):
        return TimeEstimateFormatter(self.get_estimated_exec_duration(key))

    def get_overall_time_estimate_formatter(self):
        return TimeEstimateFormatter(self.get_estimated_overall_duration())

    def add_eta_info(self, key, exec_time):
        self.results.eta_estimates[key].append(exec_time)

    def build_schedule(self):
        """Builds a queue of process execution jobs.

        Returns a set of keys which were skipped."""

        skipped = set()

        one_exec_scheduled = False
        eta_avail_job = None
        for exec_n in xrange(self.config.N_EXECUTIONS):
            for vm_name, vm_info in self.config.VMS.items():
                for bmark, param in self.config.BENCHMARKS.items():
                    for variant in vm_info["variants"]:
                        job = ExecutionJob(self, vm_name, vm_info, bmark, variant, param)
                        if not self.config.should_skip(job.key):
                            if one_exec_scheduled and not eta_avail_job:
                                # first job of second executions eta becomes known.
                                eta_avail_job = job
                                self.set_eta_avail()
                            self.add_job(job)
                        else:
                            skipped |= set([job.key])
                            if not one_exec_scheduled:
                                debug("%s is in skip list. Not scheduling." %
                                      job.key)
            one_exec_scheduled = True
        self.expected_reboots = len(self)
        # Resume mode: if previous results are available, remove the
        # jobs from the schedule which have already been executed, and
        # add the results to this object, ready to be saved to a Json file.
        if self.resume:
            self._remove_previous_execs_from_schedule()
            # Sanity check ETA estimates
            for key, exec_data in self.results.data.iteritems():
                got_len = len(self.results.eta_estimates[key])
                expect_len = len(exec_data)
                if expect_len != got_len:
                    msg = "ETA estimates didn't tally with results: "
                    msg += "key=%s, expect_len=%d, got_len=%d " % \
                        (key, expect_len, got_len)
                    msg += "data[%s]=%s; " % (key, str(self.results.data[key]))
                    msg += "eta[%s]=%s" % \
                        (key, str(self.results.eta_estimates[key]))
                    util.log_and_mail(self.mailer, error,
                                      "Fatal Krun Error",
                                      msg, bypass_limiter=True, exit=True)
        return skipped

    def _remove_previous_execs_from_schedule(self):
        for key in self.results.data:
            num_completed_jobs = self.results.jobs_completed(key)
            if num_completed_jobs > 0:
                try:
                    debug("%s has already been run %d times." %
                          (key, num_completed_jobs))
                    for _ in range(num_completed_jobs):
                        self.remove_job_by_key(key)
                        self.jobs_done += 1
                except JobMissingError as excn:
                    tup = (excn.key, self.config.filename,
                           self.config.results_filename())
                    msg = ("Failed to resume benchmarking session\n." +
                           "The execution %s appears in results " +
                           "file: %s, but not in config file: %s." % tup)
                    util.fatal(msg)

    def run(self):
        """Benchmark execution starts here"""
        jobs_left = len(self)
        if jobs_left == 0:
            debug("Krun started with an empty queue of jobs")

        if not self.started_by_init:
            util.log_and_mail(self.mailer, info,
                              "Benchmarking started",
                              "Benchmarking started.\nLogging to %s" %
                              self.log_path,
                              bypass_limiter=True)

        if self.reboot and not self.started_by_init:
            # Reboot before first benchmark (dumps results file).
            info("Reboot prior to first execution")
            self._reboot()

        if self.reboot and self.started_by_init and jobs_left > 0:
            info("Waiting %s seconds for the system to come up." %
                 str(STARTUP_WAIT_SECONDS))
            if self.dry_run:
                info("SIMULATED: time.sleep (would have waited %s seconds)." %
                     STARTUP_WAIT_SECONDS)
            else:
                time.sleep(STARTUP_WAIT_SECONDS)

        # Important that the dmesg is collected after the above startup wait.
        # Otherwise we get spurious dmesg changes.
        self.platform.collect_starting_dmesg()

        while True:
            self.platform.wait_until_cool()

            jobs_left = len(self)
            info("%d jobs left in scheduler queue" % jobs_left)
            if jobs_left == 0:
                break

            tfmt = self.get_overall_time_estimate_formatter()

            if self.eta_avail == self.jobs_done:
                # We just found out roughly how long the session has left, mail out.
                msg = "ETA for current session now known: %s" % tfmt.finish_str
                util.log_and_mail(self.mailer, info,
                             "ETA for Current Session Available",
                             msg, bypass_limiter=True)

            info("{:<25s}: {} ({} from now)".format(
                "Estimated completion", tfmt.finish_str, tfmt.delta_str))

            if (self.eta_avail is not None) and (self.jobs_done < self.eta_avail):
                info("Jobs until ETA known: %s" % self.jobs_until_eta_known())

            job = self.next_job()

            # We collect rough execution times separate from real results. The
            # reason for this is that, even if a benchmark crashes it takes
            # time and we need to account for this when making estimates. A
            # crashing benchmark will give an empty list of iteration times,
            # meaning we can't use 'raw_exec_result' below for estimates.
            exec_start_time = time.time()
            raw_exec_result = job.run(self.mailer, self.dry_run)
            exec_end_time = time.time()

            exec_result = util.format_raw_exec_results(raw_exec_result)

            if not exec_result and not self.dry_run:
                self.results.error_flag = True

            self.results.data[job.key].append(exec_result)
            self.add_eta_info(job.key, exec_end_time - exec_start_time)

            # We dump the json after each experiment so we can monitor the
            # json file mid-run. It is overwritten each time.
            info("Intermediate results dumped to %s" %
                 self.config.results_filename())
            self.results.write_to_file()

            self.jobs_done += 1
            if self.platform.check_dmesg_for_changes():
                self.results.error_flag = True

            if self.reboot and len(self) > 0:
                info("Reboot in preparation for next execution")
                self._reboot()

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

    def _reboot(self):
        self.results.reboots += 1
        debug("About to execute reboot: %g, expecting %g in total." %
              (self.results.reboots, self.expected_reboots))
        # Dump the results file. This may already have been done, but we
        # have changed self.nreboots, which needs to be written out.
        self.results.write_to_file()

        if self.results.reboots > self.expected_reboots:
            util.fatal(("HALTING now to prevent an infinite reboot loop: " +
                        "INVARIANT num_reboots <= num_jobs violated. " +
                        "Krun was about to execute reboot number: %g. " +
                        "%g jobs have been completed, %g are left to go.") %
                       (self.results.reboots, self.jobs_done, len(self)))
        if self.dry_run:
            info("SIMULATED: reboot (restarting Krun in-place)")
            args =  sys.argv
            if not self.started_by_init:
                args.extend(["--resume", "--started-by-init"])
                debug("Simulated reboot with args: " + " ".join(args))
            os.execv(args[0], args)  # replace myself
            assert False  # unreachable
        else:
            subprocess.call(self.platform.get_reboot_cmd())
