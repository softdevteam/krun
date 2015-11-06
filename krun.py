#!/usr/bin/env python2.7

"""
Benchmark, running many fresh processes.

usage: runner.py <config_file.krun>
"""

import argparse, json, logging, os, sys
from logging import debug, info, warn

import krun.util as util
from krun.platform import detect_platform
from krun.scheduler import ExecutionScheduler
from krun import ABS_TIME_FORMAT
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
    if not platform.developer_mode:
        sanity_check_user_change(platform)
    else:
        warn("Not running user change sanity check due to developer mode")


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
        _ = util.check_and_parse_execution_results(stdout, stderr, rc)
    except util.ExecutionFailed as e:
        util.fatal("%s sanity check failed: %s" % (bench_name, e.message))


def create_arg_parser():
    """Create a parser to process command-line options.
    """
    parser = argparse.ArgumentParser(description='Benchmark, running many fresh processes.')

    # Upper-case '-I' so as to make it harder to use by accident.
    # Real users should never use -I. Only the OS init system.
    parser.add_argument('--started-by-init', '-I', action='store_true',
                        default=False, dest='started_by_init', required=False,
                        help='Krun is being invoked by OS init system')
    parser.add_argument('--resume', '-r', action='store_true', default=False,
                        dest='resume', required=False,
                        help=("Resume benchmarking if interrupted " +
                              "and append to an existing results file"))
    parser.add_argument('--reboot', '-b', action='store_true', default=False,
                        dest='reboot', required=False,
                        help='Reboot before each benchmark is executed')
    parser.add_argument('--dryrun', '-d', action='store_true', default=False,
                        dest='dry_run', required=False,
                        help=("Build and run a benchmarking schedule " +
                              "But don't execute the benchmarks. " +
                              "Useful for verifying configuration files"))
    parser.add_argument('--debug', '-g', action="store", default='INFO',
                        dest='debug_level', required=False,
                        help=('Debug level used by logger. Must be one of: ' +
                              'DEBUG, INFO, WARN, DEBUG, CRITICAL, ERROR'))
    parser.add_argument('--dump-audit', action="store_true",
                        dest='dump_audit', required=False,
                        help=('Print the audit section of a Krun ' +
                              'results file to STDOUT'))
    parser.add_argument('--dump-config', action="store_true",
                        dest='dump_config', required=False,
                        help=('Print the config section of a Krun ' +
                              'results file to STDOUT'))
    parser.add_argument('--dump-reboots', action="store_true",
                        dest='dump_reboots', required=False,
                        help=('Print the reboots section of a Krun ' +
                              'results file to STDOUT'))
    parser.add_argument('--develop', action="store_true",
                        dest='develop', required=False,
                        help=('Enable developer mode'))
    filename_help = ('Krun configuration or results file. FILENAME should' +
                     ' be a configuration file when running benchmarks ' +
                     '(e.g. experiment.krun) and a results file ' +
                     '(e.g. experiment_results.json.bz2) when calling ' +
                     'krun with --dump-config, --dump_audit or ' +
                     '--dump-reboots')
    parser.add_argument('filename', action="store", # Required by default.
                        metavar='FILENAME',
                        help=(filename_help))
    return parser


def main(parser):
    args = parser.parse_args()

    if args.dump_config or args.dump_audit or args.dump_reboots:
        if not args.filename.endswith(".json.bz2"):
            usage(parser)
        else:
            results = util.read_results(args.filename)
            if args.dump_config:
                text = results['config']
            elif args.dump_audit:
                text = json.dumps(results['audit'],
                                  ensure_ascii=True, sort_keys=True,
                                  indent=4, separators=(',\n', ':\t'))
            elif args.dump_reboots:
                text = str(results['reboots'])
            print text
            sys.exit(0)

    if not args.filename.endswith(".krun"):
        usage(parser)

    try:
        if os.stat(args.filename).st_size <= 0:
            util.fatal('Krun configuration file %s is empty.' % args.filename)
    except OSError:
        util.fatal('Krun configuration file %s does not exist.' % args.filename)

    config = util.read_config(args.filename)
    out_file = util.output_name(args.filename)
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

    mail_recipients = config.get("MAIL_TO", [])
    if type(mail_recipients) is not list:
        util.fatal("MAIL_TO config should be a list")

    max_mails = config.get("MAX_MAILS", 5)
    mailer = Mailer(mail_recipients, max_mails=max_mails)

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
    for vm_name, vm_info in config["VMS"].items():
        vm_info["vm_def"].set_platform(platform)

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
        current = util.read_results(out_file)
        if not util.audits_same_platform(platform.audit, current["audit"]):
            util.fatal(error_msg)

        debug("Using pre-recorded initial temperature readings")
        platform.set_starting_temperatures(current["starting_temperatures"])
    else:
        # Touch the config file to update its mtime. This is required
        # by resume-mode which uses the mtime to determine the name of
        # the log file, should this benchmark be resumed.
        _, _, rc = util.run_shell_cmd("touch " + args.filename)
        if rc != 0:
            util.fatal("Could not touch config file: " + args.filename)

        debug("Taking fresh initial temperature readings")
        platform.set_starting_temperatures()

    log_filename = attach_log_file(args.filename, args.resume)

    sanity_checks(config, platform)

    # Build job queue -- each job is an execution
    sched = ExecutionScheduler(args.filename,
                               log_filename,
                               out_file,
                               mailer,
                               platform,
                               resume=args.resume,
                               reboot=args.reboot,
                               dry_run=args.dry_run,
                               started_by_init=args.started_by_init)
    sched.build_schedule(config, current)

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


def attach_log_file(config_filename, resume):
    log_filename = util.log_name(config_filename, resume)
    mode = 'a' if resume else 'w'
    fh = logging.FileHandler(log_filename, mode=mode)
    fh.setFormatter(PLAIN_FORMATTER)
    logging.root.addHandler(fh)
    return os.path.abspath(log_filename)


if __name__ == "__main__":
    debug("arguments: %s"  % " ".join(sys.argv[1:]))
    parser = create_arg_parser()
    setup_logging(parser)
    info("Krun starting...")
    main(parser)
