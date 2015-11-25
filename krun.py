#!/usr/bin/env python2.7

"""
Benchmark, running many fresh processes.

usage: runner.py <config_file.krun>
"""

import argparse, json, logging, os, sys
from logging import debug, info, warn
import locale

import krun.util as util
from krun.config import Config
from krun.platform import detect_platform
from krun.results import Results
from krun.scheduler import ExecutionScheduler
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
    vms_that_will_run = []
    # check all necessary benchmark files exist
    for bench, bench_param in config.BENCHMARKS.items():
        for vm_name, vm_info in config.VMS.items():
            for variant in vm_info["variants"]:
                entry_point = config.VARIANTS[variant]
                key = "%s:%s:%s" % (bench, vm_name, variant)
                debug("Running sanity check for experiment %s" % key)

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
            debug("Running sanity check for VM %s" % vm_name)
            vm_info["vm_def"].sanity_checks()

    # platform specific sanity checks
    if not platform.developer_mode:
        platform.sanity_checks()
    else:
        warn("Not running platform sanity checks due to developer mode")


def create_arg_parser():
    """Create a parser to process command-line options.
    """
    parser = argparse.ArgumentParser(description="Benchmark, running many fresh processes.")

    # Upper-case '-I' so as to make it harder to use by accident.
    # Real users should never use -I. Only the OS init system.
    parser.add_argument("--started-by-init", "-I", action="store_true",
                        default=False, dest="started_by_init", required=False,
                        help="Krun is being invoked by OS init system")
    parser.add_argument("--resume", "-r", action="store_true", default=False,
                        dest="resume", required=False,
                        help=("Resume benchmarking if interrupted " +
                              "and append to an existing results file"))
    parser.add_argument("--reboot", "-b", action="store_true", default=False,
                        dest="reboot", required=False,
                        help="Reboot before each benchmark is executed")
    parser.add_argument("--dryrun", "-d", action="store_true", default=False,
                        dest="dry_run", required=False,
                        help=("Build and run a benchmarking schedule " +
                              "But don't execute the benchmarks. " +
                              "Useful for verifying configuration files"))
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
    parser.add_argument("--develop", action="store_true",
                        dest="develop", required=False,
                        help=("Enable developer mode"))
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
            if args.dump == "config" or "audit":
                text = unicode(results.__getattribute__(args.dump))
            else:
                text = json.dumps(results.__getattribute__(args.dump),
                                  sort_keys=True, indent=2)
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
    out_file = config.results_filename()
    out_file_exists = os.path.exists(out_file)

    if out_file_exists and not os.path.isfile(out_file):
        util.fatal(
            "Output file '%s' exists but is not a regular file" % out_file)

    if out_file_exists and not args.resume:
        util.fatal("Output file '%s' already exists. "
                   "Either resume the session (--resume) or "
                   "move the file away" % out_file)

    if not out_file_exists and args.resume:
        util.fatal("No results file to resume. Expected '%s'" % out_file)

    if args.started_by_init and not args.reboot:
        util.fatal("--started-by-init makes no sense without --reboot")

    if args.started_by_init and not args.resume:
        util.fatal("--started-by-init makes no sense without --resume")

    if args.develop:
        warn("Developer mode enabled. Results will not be reliable.")

    mail_recipients = config.MAIL_TO
    if type(mail_recipients) is not list:
        util.fatal("MAIL_TO config should be a list")

    mailer = Mailer(mail_recipients, max_mails=config.MAX_MAILS)

    # Initialise platform instance and assign to VM defs.
    # This needs to be done early, so VM sanity checks can run.
    platform = detect_platform(mailer)

    if not args.develop:
        platform.check_preliminaries()
    else:
        # Needed to skip the use of certain tools and techniques.
        # E.g. taskset on Linux, and switching user.
        warn("Not checking platform prerequisites due to developer mode")
        platform.developer_mode = True

    platform.collect_audit()

    # If the user has asked for resume-mode, the current platform must
    # be an identical machine to the current one.
    error_msg = ("You have asked Krun to resume an interrupted benchmark. " +
                 "This is only valid if the machine you are using is " +
                 "identical to the one on which the last results were " +
                 "gathered, which is not the case.")
    current = None
    if args.resume:
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
        # by resume-mode which uses the mtime to determine the name of
        # the log file, should this benchmark be resumed.
        _, _, rc = util.run_shell_cmd("touch " + args.filename)
        if rc != 0:
            util.fatal("Could not touch config file: " + args.filename)

        debug("Taking fresh initial temperature readings")
        platform.starting_temperatures = platform.take_temperature_readings()

    attach_log_file(config, args.resume)

    # Assign platform to VM defs -- needs to happen early for sanity checks
    for vm_name, vm_info in config.VMS.items():
        vm_info["vm_def"].set_platform(platform)

    sanity_checks(config, platform)

    # Build job queue -- each job is an execution
    sched = ExecutionScheduler(config,
                               mailer,
                               platform,
                               resume=args.resume,
                               reboot=args.reboot,
                               dry_run=args.dry_run,
                               started_by_init=args.started_by_init)
    sched.build_schedule()

    # does the benchmarking
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
    return


if __name__ == "__main__":
    debug("arguments: %s"  % " ".join(sys.argv[1:]))
    parser = create_arg_parser()
    setup_logging(parser)
    info("Krun starting...")
    main(parser)
