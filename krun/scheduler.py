from krun.time_estimate import TimeEstimateFormatter
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

    def __init__(self, sched, config, vm_name, vm_info, benchmark, variant, parameter):
        self.sched = sched
        self.vm_name, self.vm_info = vm_name, vm_info
        self.benchmark = benchmark
        self.variant = variant
        self.parameter = parameter
        self.config = config

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
                self.parameter == other.parameter and
                self.config == other.config)

    def add_exec_time(self, exec_time):
        """Feed back a rough execution time for ETA usage"""
        self.sched.add_eta_info(self.key, exec_time)

    def run(self, mailer, dry_run=False):
        """Runs this job (execution)"""

        entry_point = self.config["VARIANTS"][self.variant]
        vm_def = self.vm_info["vm_def"]
        vm_def.set_dry_run(dry_run)

        info("Running '%s(%d)' (%s variant) under '%s'" %
                    (self.benchmark, self.parameter, self.variant, self.vm_name))

        # Print ETA for execution if available
        tfmt = self.get_exec_estimate_time_formatter()
        info("{:<35s}: {} ({} from now)".format(
                                         "Estimated completion (this exec)",
                                         tfmt.finish_str,
                                         tfmt.delta_str))

        # Set heap limit
        heap_limit_kb = self.config["HEAP_LIMIT"]
        heap_limit_b = heap_limit_kb * 1024  # resource module speaks in bytes
        heap_t = (heap_limit_b, heap_limit_b)
        resource.setrlimit(resource.RLIMIT_DATA, heap_t)
        assert resource.getrlimit(resource.RLIMIT_DATA) == heap_t

        # Rough ETA execution timer
        exec_start_rough = time.time()
        stdout, stderr, rc = vm_def.run_exec(
            entry_point, self.benchmark, self.vm_info["n_iterations"],
            self.parameter, heap_limit_kb)
        exec_time_rough = time.time() - exec_start_rough

        if not dry_run:
            try:
                iterations_results = util.check_and_parse_execution_results(stdout, stderr, rc)
            except util.ExecutionFailed as e:
                util.log_and_mail(mailer, error, "Benchmark failure: %s" % self.key, e.message)
                iterations_results = []

            # Add to ETA estimation figures
            # Note we still add a time estimate even if the benchmark crashed.
            self.add_exec_time(exec_time_rough)

            return iterations_results

        else:
            return []


class ExecutionScheduler(object):
    """Represents our entire benchmarking session"""

    def __init__(self, config_file, log_filename, out_file, mailer, platform,
                 resume=False, reboot=False, dry_run=False,
                 started_by_init=False):
        self.mailer = mailer

        self.work_deque = deque()
        self.eta_avail = None
        self.jobs_done = 0
        self.platform = platform
        self.resume = resume
        self.reboot = reboot
        self.dry_run = dry_run
        self.started_by_init = started_by_init

        # Record how long processes are taking so we can make a
        # rough ETA for the user.
        # Maps "bmark:vm:variant" -> [t_0, t_1, ...]
        self.eta_estimates = {}

        # Maps key to results:
        # "bmark:vm:variant" -> [[e0i0, e0i1, ...], [e1i0, e1i1, ...], ...]
        self.results = {}

        # file names
        self.config_file = config_file
        self.out_file = out_file
        self.log_path = log_filename

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
        debug("DEBUG: Removed %s from schedule" % key)
        self.work_deque.remove(job_to_remove)

    def next_job(self):
        try:
            return self.work_deque.popleft()
        except IndexError:
            raise ScheduleEmpty() # we are done

    def __len__(self):
        return len(self.work_deque)

    def get_estimated_exec_duration(self, key):
        previous_exec_times = self.eta_estimates.get(key)
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
        self.eta_estimates[key].append(exec_time)

    def build_schedule(self, config, current_result_json):
        one_exec_scheduled = False
        eta_avail_job = None
        for exec_n in xrange(config["N_EXECUTIONS"]):
            for vm_name, vm_info in config["VMS"].items():
                for bmark, param in config["BENCHMARKS"].items():
                    for variant in vm_info["variants"]:
                        job = ExecutionJob(self, config, vm_name, vm_info, bmark, variant, param)
                        if not util.should_skip(config, job.key):
                            if one_exec_scheduled and not eta_avail_job:
                                # first job of second executions eta becomes known.
                                eta_avail_job = job
                                self.set_eta_avail()
                            self.add_job(job)
                        else:
                            if not one_exec_scheduled:
                                debug("DEBUG: %s is in skip list. Not scheduling." %
                                      job.key)
            one_exec_scheduled = True
        # Resume mode: if previous results are available, remove the
        # jobs from the schedule which have already been executed, and
        # add the results to this object, ready to be saved to a Json file.
        if self.resume and current_result_json is not None:
            for key in current_result_json['data']:
                num_completed_jobs = len(current_result_json['data'][key])
                if num_completed_jobs > 0:
                    try:
                        debug("DEBUG: %s has already been run %g times." %
                              (key, num_completed_jobs))
                        for _ in range(num_completed_jobs):
                            self.remove_job_by_key(key)
                            self.jobs_done += 1
                        self.eta_estimates[key] = []
                        for result_set in current_result_json['data'][key]:
                            total_time = sum(result_set)
                            self.eta_estimates[key].append(total_time)
                    except JobMissingError as excn:
                        tup = (excn.key, self.config_file, self.out_file)
                        msg = ("Failed to resume benchmarking session\n." +
                               "The execution %s appears in results " +
                               "file: %s, but not in config file: %s." % tup)
                        util.fatal(msg)
                    self.results[key] = current_result_json['data'][key]

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

        # scaffold dicts
        for job in self.work_deque:
            if not job.key in self.eta_estimates:
                self.eta_estimates[job.key] = []
            if not job.key in self.results:
                self.results[job.key] = []

        if self.reboot and not self.started_by_init:
            # This has the effect of making a blank results file
            # if it doesn't yet exist. If it does exist, then
            # this is actually a no-op. As the same information
            # will be written back to the results file.
            util.dump_results(self.config_file, self.out_file,
                              self.results, self.platform.audit)
            # and reboot before first benchmark
            info("Reboot prior to first execution")
            self._reboot()

        if self.reboot and self.started_by_init and jobs_left > 0:
            info("Waiting %sseconds for the network to come up." %
                 str(STARTUP_WAIT_SECONDS))
            if self.dry_run:
                info("SIMULATED: time.sleep (would have waited %gsecs)." %
                     STARTUP_WAIT_SECONDS)
            else:
                time.sleep(STARTUP_WAIT_SECONDS)

        errors = False # XXX not preserved across reboots!
        start_time = time.time() # rough overall timer, not used for actual results

        while True:
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
            raw_exec_result = job.run(self.mailer, self.dry_run)
            exec_result = util.format_raw_exec_results(raw_exec_result)

            if not exec_result and not self.dry_run:
                errors = True

            self.results[job.key].append(exec_result)

            # We dump the json after each experiment so we can monitor the
            # json file mid-run. It is overwritten each time.
            info("Intermediate results dumped to %s" % self.out_file)
            util.dump_results(self.config_file, self.out_file, self.results,
                              self.platform.audit)

            self.jobs_done += 1
            self.platform.wait_until_cpu_cool()
            self.platform.check_dmesg_for_changes()

            if self.reboot and len(self) > 0:
                info("Reboot in preparation for next execution")
                self._reboot()

        end_time = time.time() # rough overall timer, not used for actual results

        self.platform.print_all_dmesg_changes()
        self.platform.save_power()

        info("Done: Results dumped to %s" % self.out_file)
        if errors:
            warn("Errors occurred --  read the log!")

        msg = "Completed in (roughly) %f seconds.\nLog file at: %s" % \
            ((end_time - start_time), self.log_path)
        util.log_and_mail(self.mailer, info, "Benchmarks Complete", msg,
                          bypass_limiter=True)

    def _reboot(self):
        if self.dry_run:
            info("SIMULATED: reboot (restarting Krun in-place)")
            args = [sys.executable, sys.argv[0],
                    "--started-by-init", "--resume", "--dryrun",
                    "--reboot", self.config_file]
            os.execv(args[0], args)  # replace myself
            assert False  # unreachable
        else:
            subprocess.call(self.platform.get_reboot_cmd())
