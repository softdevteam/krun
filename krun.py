#!/usr/bin/env python2.7

"""
Benchmark, running many fresh processes.

usage: runner.py <config_file.krun>
"""

import os, sys, json, time
import logging
from collections import deque
import datetime
import resource
from logging import warn, info, error, debug

import krun.util as util
from krun.util import log_and_mail, log_name, fatal
from krun.platform import detect_platform
from krun import ABS_TIME_FORMAT, UNKNOWN_TIME_DELTA, UNKNOWN_ABS_TIME
from krun.mail import Mailer

BENCH_DRYRUN = os.environ.get("BENCH_DRYRUN", False)

HERE = os.path.abspath(os.getcwd())


try:
    import colorlog
    COLOURS = True
except ImportError:
    COLOURS = False

COLOUR_FORMATTER = colorlog.ColoredFormatter(
    "%(log_color)s[%(asctime)s %(levelname)s] %(message)s%(reset)s",
    ABS_TIME_FORMAT)
PLAIN_FORMATTER = logging.Formatter(
    '[%(asctime)s: %(levelname)s] %(message)s',
    ABS_TIME_FORMAT)

if COLOURS:
    CONSOLE_FORMATTER = COLOUR_FORMATTER
else:
    CONSOLE_FORMATTER = PLAIN_FORMATTER

def usage():
    print(__doc__)
    sys.exit(1)

def mean(seq):
    return sum(seq) / float(len(seq))

def dump_json(config_file, out_file, all_results, audit):
    # dump out into json file, incluing contents of the config file
    with open(config_file, "r") as f:
        config_text = f.read()

    to_write = {"config": config_text, "data": all_results, "audit": audit}

    with open(out_file, "w") as f:
        f.write(json.dumps(to_write, indent=1, sort_keys=True))

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

    def add_exec_time(self, exec_time):
        """Feed back a rough execution time for ETA usage"""
        self.sched.add_eta_info(self.key, exec_time)

    def run(self, mailer):
        """Runs this job (execution)"""

        entry_point = self.config["VARIANTS"][self.variant]
        vm_def = self.vm_info["vm_def"]

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

        eval_exn = None
        try:
            iterations_results = eval(stdout) # we should get a list of floats
        except Exception as e:  # eval can raise any Python exception
            eval_exn = e

        if eval_exn or rc != 0:
            # Something went wrong
            rule = 50 * "-"
            err_s = ("Benchmark returned non-zero or didn't emit a "
                     "parsable list on stdout.\n")
            if eval_exn:
                err_s += "Exception string: %s\n" % str(e)
            err_s += "return code: %d\n" % rc
            err_s += "stdout:\n%s\n%s\n%s\n\n" % (rule, stdout, rule)
            err_s += "stderr:\n%s\n%s\n%s\n" % (rule, stderr, rule)
            log_and_mail(mailer, error, "Benchmark failure: %s" % self.key, err_s)
            iterations_results = []
        else:
            # Note that because we buffered stderr, we will be seeing the
            # 'iteration x/y' message from the iterations runner *after*
            # each iteration, not before.
            info(stderr)

        # Add to ETA estimation figures
        # Note we still add a time estimate even if the benchmark crashed.
        self.add_exec_time(exec_time_rough)

        return iterations_results


class ScheduleEmpty(Exception):
    pass

class ExecutionScheduler(object):
    """Represents our entire benchmarking session"""

    def __init__(self, config_file, out_file, mailer, platform):
        self.mailer = mailer

        self.work_deque = deque()
        self.eta_avail = None
        self.jobs_done = 0
        self.platform = platform

        # Record how long processes are taking so we can make a
        # rough ETA for the user.
        # Maps (bmark, vm, variant) -> [t_0, t_1, ...]
        self.eta_estimates = {}

        # Maps key to results:
        # (bmark, vm, variant) -> [[e0i0, e0i1, ...], [e1i0, e1i1, ...], ...]
        self.results = {}

        # file names
        self.config_file = config_file
        self.out_file = out_file
        self.log_path = os.path.abspath(log_name(self.config_file))

    def set_eta_avail(self):
        """call after adding job before eta should become available"""
        self.eta_avail = len(self)

    def jobs_until_eta_known(self):
        return self.eta_avail - self.jobs_done

    def add_job(self, job):
        self.work_deque.append(job)

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

    def run(self):
        """Benchmark execution starts here"""

        log_and_mail(self.mailer, info,
                     "Benchmarking started",
                     "Benchmarking started.\nLogging to %s" % self.log_path,
                     bypass_limiter=True)

        # scaffold dicts
        for j in self.work_deque:
            self.eta_estimates[j.key] = []
            self.results[j.key] = []

        errors = False
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
                log_and_mail(self.mailer, info,
                             "ETA for Current Session Available",
                             msg, bypass_limiter=True)

            info("{:<25s}: {} ({} from now)".format(
                "Estimated completion", tfmt.finish_str, tfmt.delta_str))

            if (self.eta_avail is not None) and (self.jobs_done < self.eta_avail):
                info("Jobs until ETA known: %s" % self.jobs_until_eta_known())

            job = self.next_job()
            exec_result = job.run(self.mailer)

            if not exec_result and not BENCH_DRYRUN:
                errors = True

            self.results[job.key].append(exec_result)

            # We dump the json after each experiment so we can monitor the
            # json file mid-run. It is overwritten each time.
            dump_json(self.config_file, self.out_file, self.results,
                      self.platform.audit)

            self.jobs_done += 1
            self.platform.wait_until_cpu_cool()
            self.platform.check_dmesg_for_changes()

        end_time = time.time() # rough overall timer, not used for actual results

        self.platform.print_all_dmesg_changes()
        self.platform.save_power()

        info("Done: Results dumped to %s" % self.out_file)
        if errors:
            warn("Errors occurred --  read the log!")

        msg = "Completed in (roughly) %f seconds.\nLog file at: %s" % \
            ((end_time - start_time), self.log_path)
        log_and_mail(self.mailer, info, "Benchmarks Complete", msg,
                     bypass_limiter=True)

class TimeEstimateFormatter(object):
    def __init__(self, seconds):
        """Generates string representations of time estimates.
        Args:
        seconds -- estimated seconds into the future. None for unknown.
        """
        self.start = datetime.datetime.now()
        if seconds is not None:
            self.delta = datetime.timedelta(seconds=seconds)
            self.finish = self.start + self.delta
        else:
            self.delta = None
            self.finish = None

    @property
    def start_str(self):
        return str(self.start.strftime(ABS_TIME_FORMAT))

    @property
    def finish_str(self):
        if self.finish is not None:
            return str(self.finish.strftime(ABS_TIME_FORMAT))
        else:
            return UNKNOWN_ABS_TIME

    @property
    def delta_str(self):
        if self.delta is not None:
            return str(self.delta).split(".")[0]
        else:
            return UNKNOWN_TIME_DELTA

def sanity_checks(config):
    vms_that_will_run = []
    # check all necessary benchmark files exist
    for bench, bench_param in config["BENCHMARKS"].items():
        for vm_name, vm_info in config["VMS"].items():
            for variant in vm_info["variants"]:
                entry_point = config["VARIANTS"][variant]
                key = "%s:%s:%s" % (bench, vm_name, variant)
                debug("Running sanity check for experiment %s" % key)

                if util.should_skip(config, key):
                    continue  # won't execute, so no check needed

                vm_info["vm_def"].check_benchmark_files(bench, entry_point)
                vms_that_will_run.append(vm_name)

    # per-VM sanity checks
    for vm_name, vm_info in config["VMS"].items():
        if vm_name not in vms_that_will_run:
            # User's SKIP config directive may mean a defined VM never runs.
            # This may be deliberate, e.g. the user does not yet have it built.
            # In this case, sanity checks can't run for this VM, so skip them.
            debug("VM '%s' is not used, not sanity checking." % vm_name)
        else:
            debug("Running sanity check for VM %s" % vm_name)
            vm_info["vm_def"].sanity_checks()


def main():
    try:
        config_file = sys.argv[1]
    except IndexError:
        usage()

    if not config_file.endswith(".krun"):
        usage()

    config = util.read_config(config_file)
    out_file = util.output_name(config_file)

    mail_recipients = config.get("MAIL_TO", [])
    if type(mail_recipients) is not list:
        fatal("MAIL_TO config should be a list")

    max_mails = config.get("MAX_MAILS", 5)
    mailer = Mailer(mail_recipients, max_mails=max_mails)

    # Initialise platform instance and assign to VM defs.
    # This needs to be done early, so VM sanity checks can run.
    platform = detect_platform(mailer)
    platform.check_preliminaries()
    platform.set_base_cpu_temps()
    platform.collect_audit()
    for vm_name, vm_info in config["VMS"].items():
        vm_info["vm_def"].set_platform(platform)

    attach_log_file(config_file)

    sanity_checks(config)

    # Build job queue -- each job is an execution
    one_exec_scheduled = False
    sched = ExecutionScheduler(config_file, out_file, mailer, platform)

    eta_avail_job = None
    for exec_n in xrange(config["N_EXECUTIONS"]):
        for vm_name, vm_info in config["VMS"].items():
            for bmark, param in config["BENCHMARKS"].items():
                for variant in vm_info["variants"]:
                    job = ExecutionJob(sched, config, vm_name, vm_info, bmark, variant, param)

                    if not util.should_skip(config, job.key):
                        if one_exec_scheduled and not eta_avail_job:
                            eta_avail_job = job # first job of second executions eta becomes known.
                            sched.set_eta_avail()
                        sched.add_job(job)
                    else:
                        if not one_exec_scheduled:
                            debug("DEBUG: %s is in skip list. Not scheduling." %
                                  job.key)
        one_exec_scheduled = True

    sched.run() # does the benchmarking

def setup_logging():
    # Colours help to distinguish benchmark stderr from messages printed
    # by the runner. We also print warnings and errors in red so that it
    # is quite impossible to miss them.

    # We default to "info" level, user can change by setting
    # KRUN_DEBUG in the environment.
    level_str = os.environ.get("KRUN_DEBUG", "info").upper()
    if level_str not in ("DEBUG", "INFO", "WARN", "DEBUG", "CRITICAL", "ERROR"):
        fatal("Bad debug level: %s" % level_str)

    level = getattr(logging, level_str.upper())

    logging.root.setLevel(level)
    stream = logging.StreamHandler()
    stream.setLevel(level)
    stream.setFormatter(CONSOLE_FORMATTER)
    logging.root.addHandler(stream)


def attach_log_file(config_filename):
    fh = logging.FileHandler(log_name(config_filename), mode='w')
    fh.setFormatter(PLAIN_FORMATTER)
    logging.root.addHandler(fh)

if __name__ == "__main__":
    setup_logging()
    main()
