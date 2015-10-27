#!/usr/bin/env python2.7

"""
Benchmark, running many fresh processes.

usage: runner.py <config_file.krun>
"""

import argparse
import os, sys, time
import logging
from collections import deque
import datetime
import resource
import subprocess
from logging import warn, info, error, debug

import krun.util as util
from krun.platform import detect_platform
from krun import ABS_TIME_FORMAT, UNKNOWN_TIME_DELTA, UNKNOWN_ABS_TIME
from krun.mail import Mailer

HERE = os.path.abspath(os.getcwd())
DIR = os.path.abspath(os.path.dirname(__file__))
MISC_SANITY_CHECK_DIR = os.path.join(DIR, "misc_sanity_checks")


CONSOLE_FORMATTER = PLAIN_FORMATTER = logging.Formatter(
    '[%(asctime)s: %(levelname)s] %(message)s',
    ABS_TIME_FORMAT)
try:
    import colorlog
    CONSOLE_FORMATTER = colorlog.ColoredFormatter(
        "%(log_color)s[%(asctime)s %(levelname)s] %(message)s%(reset)s",
        ABS_TIME_FORMAT)
except ImportError:
    pass


def usage(parser):
    parser.print_help()
    sys.exit(1)

def mean(seq):
    return sum(seq) / float(len(seq))


class JobMissingError(Exception):
    """This is exception is called by the scheduler, in resume mode.
    This exception should be raised when  the user has asked to
    resume an interrupted benchmark, and the json results contain
    an execution that does not appear in the config file.
    """
    def __init__(self, key):
        self.key = key


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


class ScheduleEmpty(Exception):
    pass

class ExecutionScheduler(object):
    """Represents our entire benchmarking session"""

    def __init__(self, config_file, log_filename, out_file, mailer, platform,
                 resume=False, reboot=False):
        self.mailer = mailer

        self.work_deque = deque()
        self.eta_avail = None
        self.jobs_done = 0
        self.platform = platform
        self.resume = resume
        self.reboot = reboot

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
                if len(current_result_json['data'][key]) > 0:
                    try:
                        self.remove_job_by_key(key)
                        debug("DEBUG: %s has already been run. Not scheduling." %
                               key)
                    except JobMissingError as excn:
                        tup = (excn.key, self.config_file, self.out_file)
                        msg = ("Failed to resume benchmarking session\n." +
                               "The execution %s appears in results " +
                               "file: %s, but not in config file: %s." % tup)
                        util.fatal(msg)
                    self.results[key] = current_result_json['data'][key]

    def run(self, dry_run=False):
        """Benchmark execution starts here"""

        util.log_and_mail(self.mailer, info,
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
                util.log_and_mail(self.mailer, info,
                             "ETA for Current Session Available",
                             msg, bypass_limiter=True)

            info("{:<25s}: {} ({} from now)".format(
                "Estimated completion", tfmt.finish_str, tfmt.delta_str))

            if (self.eta_avail is not None) and (self.jobs_done < self.eta_avail):
                info("Jobs until ETA known: %s" % self.jobs_until_eta_known())

            job = self.next_job()
            raw_exec_result = job.run(self.mailer, dry_run)
            exec_result = util.format_raw_exec_results(raw_exec_result)

            if not exec_result and not dry_run:
                errors = True

            self.results[job.key].append(exec_result)

            # We dump the json after each experiment so we can monitor the
            # json file mid-run. It is overwritten each time.
            util.dump_results(self.config_file, self.out_file, self.results,
                              self.platform.audit)

            self.jobs_done += 1
            self.platform.wait_until_cpu_cool()
            self.platform.check_dmesg_for_changes()

            if self.reboot and dry_run:
                subprocess.call(['echo'] + self.platform.get_reboot_cmd())
            elif self.reboot:
                subprocess.call(self.platform.get_reboot_cmd())

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


def sanity_checks(config, platform):
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

    # misc sanity checks
    sanity_check_user_change(platform)


# This can be modularised if we add more misc sanity checks
def sanity_check_user_change(platform):
    """Run a dummy benchmark which crashes if the it doesn't appear to be
    running as the krun user"""

    debug("running user change sanity check")

    from krun.vm_defs import PythonVMDef, SANITY_CHECK_HEAP_KB
    from krun import EntryPoint

    bench_name = "user change"
    iterations = 1
    param = 666

    ep = EntryPoint("check_user_change.py", subdir=MISC_SANITY_CHECK_DIR)
    vd = PythonVMDef(sys.executable)  # run under the VM that runs *this*
    vd.set_platform(platform)

    stdout, stderr, rc = \
        vd.run_exec(ep, bench_name, iterations, param, SANITY_CHECK_HEAP_KB)

    try:
        times = util.check_and_parse_execution_results(stdout, stderr, rc)
    except util.ExecutionFailed as e:
        util.fatal("%s sanity check failed: %s" % (bench_name, e.message))


def create_arg_parser():
    """Create a parser to process command-line options.
    """
    parser = argparse.ArgumentParser(description='Benchmark, running many fresh processes.')
    parser.add_argument('--resume', '-r', action='store_true', default=False,
                        dest='resume', required=False,
                        help='Resume benchmarking if interrupted')
    parser.add_argument('--reboot', '-b', action='store_true', default=False,
                        dest='reboot', required=False,
                        help='Reboot after every execution')
    parser.add_argument('--dryrun', '-d', action='store_true', default=False,
                        dest='dry_run', required=False,
                        help=("Don't execute benchmarks. " +
                              "Useful for verifying configuration files."))
    parser.add_argument('--debug', '-g', action="store", default='INFO',
                        dest='debug_level', required=False,
                        help=('Debug level used by logger. Must be one of: ' +
                              'DEBUG, INFO, WARN, DEBUG, CRITICAL, ERROR'))
    parser.add_argument('config', action="store", # Required by default.
                        metavar='FILENAME',
                        help='krun configuration file, e.g. experiment.krun')
    return parser

def main(parser):
    args = parser.parse_args()

    if not args.config.endswith(".krun"):
        usage(parser)

    try:
        if os.stat(args.config).st_size <= 0:
            util.fatal('krun configuration file %s is empty.' % args.config)
    except OSError:
        util.fatal('krun configuration file %s does not exist.' % args.config)

    config = util.read_config(args.config)
    out_file = util.output_name(args.config)

    mail_recipients = config.get("MAIL_TO", [])
    if type(mail_recipients) is not list:
        util.fatal("MAIL_TO config should be a list")

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

    # If the user has asked for resume-mode, the current platform must
    # be an identical machine to the current one.
    error_msg = ("You have asked krun to resume an interrupted benchmark. " +
                 "This is only valid if the machine you are using is " +
                 "identical to the one on which the last results were " +
                 "gathered, which is not the case.")
    current = None
    if args.resume:
        if os.path.isfile(out_file):
            current = util.read_results(out_file)
            if not util.audits_same_platform(platform.audit, current["audit"]):
                util.fatal(error_msg)
        else:
            # Touch the config file to update its mtime. This is required
            # by resume-mode which uses the mtime to determine the name of
            # the log file, should this benchmark be resumed.
            _, _, rc = util.run_shell_cmd("touch " + args.config)
            if rc > 0:
                util.fatal("Could not touch config file: " + args.config)

    log_filename = attach_log_file(args.config, args.resume)

    sanity_checks(config, platform)

    # Build job queue -- each job is an execution
    sched = ExecutionScheduler(args.config,
                               log_filename,
                               out_file,
                               mailer,
                               platform,
                               resume=args.resume,
                               reboot=args.reboot)
    sched.build_schedule(config, current)
    sched.run(args.dry_run) # does the benchmarking

def setup_logging(parser):
    # Colours help to distinguish benchmark stderr from messages printed
    # by the runner. We also print warnings and errors in red so that it
    # is quite impossible to miss them.
    args = parser.parse_args()

    # We default to "info" level, user can change by setting
    # KRUN_DEBUG in the environment.
    level_str = args.debug_level.upper()
    if level_str not in ("DEBUG", "INFO", "WARN", "DEBUG", "CRITICAL", "ERROR"):
        util.fatal("Bad debug level: %s" % level_str)

    level = getattr(logging, level_str.upper())

    logging.root.setLevel(level)
    stream = logging.StreamHandler()
    stream.setLevel(level)
    stream.setFormatter(CONSOLE_FORMATTER)
    logging.root.addHandler(stream)


def attach_log_file(config_filename, resume):
    log_filename = util.log_name(config_filename, resume)
    mode = 'a' if resume else 'w'
    fh = logging.FileHandler(log_filename, mode=mode)
    fh.setFormatter(PLAIN_FORMATTER)
    logging.root.addHandler(fh)
    return os.path.abspath(log_filename)

if __name__ == "__main__":
    parser = create_arg_parser()
    setup_logging(parser)
    main(parser)
