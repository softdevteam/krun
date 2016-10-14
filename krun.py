#!/usr/bin/env python2.7

"""
Benchmark, running many fresh processes.

usage: runner.py <config_file.krun>
"""

import argparse, logging, os, sys
from logging import debug, info, warn
import locale

import krun.util as util
from krun.config import Config
from krun.platform import detect_platform
from krun.results import Results
from krun.scheduler import ExecutionScheduler, ManifestManager
from krun import ABS_TIME_FORMAT
from krun.mail import Mailer

HERE = os.path.abspath(os.getcwd())
DIR = os.path.abspath(os.path.dirname(__file__))

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


def sanity_checks(config, platform):
    debug("Running sanity checks")

    vms_that_will_run = []
    # check all necessary benchmark files exist
    for bench, bench_param in config.BENCHMARKS.items():
        for vm_name, vm_info in config.VMS.items():
            for variant in vm_info["variants"]:
                entry_point = config.VARIANTS[variant]
                key = "%s:%s:%s" % (bench, vm_name, variant)
                debug("Sanity check files for '%s'" % key)

                if config.should_skip(key):
                    continue  # won't execute, so no check needed

                vm_info["vm_def"].check_benchmark_files(bench, entry_point)
                vms_that_will_run.append(vm_name)

    # per-VM sanity checks
    for vm_name, vm_info in config.VMS.items():
        if vm_name not in vms_that_will_run:
            # User's SKIP config directive may mean a defined VM never runs.
            # This may be deliberate, e.g. the user does not yet have it built.
            # In this case, sanity checks can't run for this VM, so skip them.
            debug("VM '%s' is not used, not sanity checking." % vm_name)
        else:
            debug("Running VM sanity check for '%s'" % vm_name)
            vm_info["vm_def"].sanity_checks()

    # platform specific sanity checks
    debug("Running platform sanity checks")
    platform.sanity_checks()


def create_arg_parser():
    """Create a parser to process command-line options.
    """
    parser = argparse.ArgumentParser(description="Benchmark, running many fresh processes.")

    parser.add_argument("--debug", "-g", action="store", default='INFO',
                        dest="debug_level", required=False,
                        help=("Debug level used by logger. Must be one of: " +
                              "DEBUG, INFO, WARN, DEBUG, CRITICAL, ERROR"))
    parser.add_argument("--dump-audit", action="store_const",
                        dest="dump", const="audit", required=False,
                        help=("Print the audit section of a Krun " +
                              "results file to STDOUT"))
    parser.add_argument("--dump-config", action="store_const",
                        dest="dump", const="config", required=False,
                        help=("Print the config section of a Krun " +
                              "results file to STDOUT"))
    parser.add_argument("--dump-reboots", action="store_const",
                        dest="dump", const="reboots", required=False,
                        help=("Print the reboots section of a Krun " +
                              "results file to STDOUT"))
    parser.add_argument("--dump-etas", action="store_const",
                        dest="dump", const="eta_estimates", required=False,
                        help=("Print the eta_estimates section of a Krun " +
                              "results file to STDOUT"))
    parser.add_argument("--dump-temps", action="store_const",
                        dest="dump", const="starting_temperatures",
                        required=False,
                        help=("Print the starting_temperatures section of " +
                              "a Krun results file to STDOUT"))
    parser.add_argument("--dump-data", action="store_const",
                        dest="dump", const="data", required=False,
                        help=("Print the data section of " +
                              "a Krun results file to STDOUT"))
    parser.add_argument("--info", action="store_true",
                        help=("Print session info for specified "
                              "config file and exit"))

    # Developer switches
    parser.add_argument("--quick", action="store_true", default=False,
                        help="No delays. For development only.")
    parser.add_argument("--no-user-change", action="store_true", default=False,
                        help="Do not change user to benchmark. "
                        "For development only.")
    parser.add_argument("--dry-run", "-d", action="store_true", default=False,
                        help=("Don't really run benchmarks. "
                              "For development only."))
    parser.add_argument("--no-pstate-check", action="store_true", default=False,
                        help=("Don't check Intel P-states are disabled in the"
                              "Linux kernel. For development only."))
    parser.add_argument("--no-tickless-check", action="store_true", default=False,
                        help=("Don't check if the Linux kernel is tickless. "
                              "Linux kernel. For development only."))
    parser.add_argument("--hardware-reboots", action="store_true", default=False,
                        help=("Reboot physical hardware before each benchmark "
                              "execution. Off by default."))

    filename_help = ("Krun configuration or results file. FILENAME should" +
                     " be a configuration file when running benchmarks " +
                     "(e.g. experiment.krun) and a results file " +
                     "(e.g. experiment_results.json.bz2) when calling " +
                     "krun with --dump-config, --dump_audit, " +
                     "--dump-reboots, --dump-etas, --dump-temps, or"
                     "--dump-data")
    parser.add_argument("filename", action="store", # Required by default.
                        metavar="FILENAME",
                        help=(filename_help))
    return parser


def main(parser):
    args = parser.parse_args()

    if args.dump is not None:
        if not args.filename.endswith(".json.bz2"):
            usage(parser)
        else:
            results = Results(None, None, results_file=args.filename)
            text = results.dump(args.dump)
            # String data read in from JSON are unicode objects. This matters
            # for us as some data in the audit includes unicode characters.
            # If it does, a simple print no longer suffices if the system
            # locale is (e.g.) ASCII. In this case print will raise an
            # exception. The correct thing to do is to encode() the unicode to
            # the system locale.
            print(text.encode(locale.getpreferredencoding()))
            sys.exit(0)

    if not args.filename.endswith(".krun"):
        usage(parser)

    try:
        if os.stat(args.filename).st_size <= 0:
            util.fatal('Krun configuration file %s is empty.' % args.filename)
    except OSError:
        util.fatal('Krun configuration file %s does not exist.' % args.filename)

    config = Config(args.filename)

    if args.info:
        # Info mode doesn't run the experiment.
        # Just prints some metrics and exits.
        util.print_session_info(config)
        return

    on_first_invocation = not (os.path.isfile(ManifestManager.PATH) and
                               os.stat(ManifestManager.PATH).st_size > 0)

    attach_log_file(config, not on_first_invocation)
    debug("Krun invoked with arguments: %s" % sys.argv)

    mail_recipients = config.MAIL_TO
    if type(mail_recipients) is not list:
        util.fatal("MAIL_TO config should be a list")

    mailer = Mailer(mail_recipients, max_mails=config.MAX_MAILS)

    try:
        inner_main(mailer, on_first_invocation, config, args)
    except util.FatalKrunError as e:
        util.run_shell_cmd_list(config.POST_EXECUTION_CMDS)
        subject = "Fatal Krun Exception"
        mailer.send(subject, e.args[0], bypass_limiter=True)
        raise e


def inner_main(mailer, on_first_invocation, config, args):
    out_file = config.results_filename()
    out_file_exists = os.path.exists(out_file)

    if out_file_exists and not os.path.isfile(out_file):
        util.fatal(
            "Output file '%s' exists but is not a regular file" % out_file)

    if out_file_exists and on_first_invocation:
        util.fatal("Output results file '%s' already exists. "
                   "Move the file away before running Krun." % out_file)

    if not out_file_exists and not on_first_invocation:
        util.fatal("No results file to resume. Expected '%s'" % out_file)

    # Initialise platform instance and assign to VM defs.
    # This needs to be done early, so VM sanity checks can run.
    platform = detect_platform(mailer, config)

    platform.quick_mode = args.quick
    platform.no_user_change = args.no_user_change
    platform.no_tickless_check = args.no_tickless_check
    platform.no_pstate_check = args.no_pstate_check
    platform.hardware_reboots = args.hardware_reboots

    debug("Checking platform preliminaries")
    platform.check_preliminaries()

    # Make a bit of noise if this is a virtualised environment
    if platform.is_virtual():
        warn("This appears to be a virtualised host. The results will be flawed. "
             "Use bare-metal for reliable results!")

    platform.collect_audit()

    # If the user has asked for resume-mode, the current platform must
    # be an identical machine to the current one.
    error_msg = ("You have asked Krun to resume an interrupted benchmark. " +
                 "This is only valid if the machine you are using is " +
                 "identical to the one on which the last results were " +
                 "gathered, which is not the case.")
    current = None
    if not on_first_invocation:
        # output file must exist, due to check above
        assert(out_file_exists)
        current = Results(config, platform, results_file=out_file)
        from krun.audit import Audit
        if not Audit(platform.audit) == current.audit:
            util.fatal(error_msg)

        debug("Using pre-recorded initial temperature readings")
        platform.starting_temperatures = current.starting_temperatures
    else:
        # Touch the config file to update its mtime. This is required
        # by when resuming a partially complete benchmark session, in which
        # case Krun uses the mtime to determine the name of the log file.
        _, _, rc = util.run_shell_cmd("touch " + args.filename)
        if rc != 0:
            util.fatal("Could not touch config file: " + args.filename)

        info(("Wait %s secs to allow system to cool prior to "
             "collecting initial temperature readings") %
             config.TEMP_READ_PAUSE)
        platform.sleep(config.TEMP_READ_PAUSE)

        debug("Taking fresh initial temperature readings")
        platform.starting_temperatures = platform.take_temperature_readings()

    # Assign platform to VM defs -- needs to happen early for sanity checks
    util.assign_platform(config, platform)

    sanity_checks(config, platform)

    # Build job queue -- each job is an execution
    sched = ExecutionScheduler(config,
                               mailer,
                               platform,
                               dry_run=args.dry_run,
                               on_first_invocation=on_first_invocation)
    sched.run()


def setup_logging(parser):
    # Colours help to distinguish benchmark stderr from messages printed
    # by the runner. We also print warnings and errors in red so that it
    # is quite impossible to miss them.
    args = parser.parse_args()

    # We default to "info" level, user can change by passing
    # in a different argument to --debug on the command line.
    level_str = args.debug_level.upper()
    if level_str not in ("DEBUG", "INFO", "WARN", "DEBUG", "CRITICAL", "ERROR"):
        util.fatal("Bad debug level: %s" % level_str)

    level = getattr(logging, level_str.upper())

    logging.root.setLevel(level)
    stream = logging.StreamHandler()
    stream.setLevel(level)
    stream.setFormatter(CONSOLE_FORMATTER)
    logging.root.handlers = [stream]


def attach_log_file(config, resume):
    log_filename = config.log_filename(resume)
    mode = 'a' if resume else 'w'
    fh = logging.FileHandler(log_filename, mode=mode)
    fh.setFormatter(PLAIN_FORMATTER)
    logging.root.addHandler(fh)
    debug("Attached log file: %s" % log_filename)


if __name__ == "__main__":
    debug("Krun starting...")
    debug("arguments: %s"  % " ".join(sys.argv[1:]))
    parser = create_arg_parser()
    setup_logging(parser)

    try:
        main(parser)
    except util.FatalKrunError as e:
        sys.exit(1)
