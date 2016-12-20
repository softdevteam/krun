from krun.time_estimate import TimeEstimateFormatter, now_str
from krun.results import Results
from krun import util

from logging import warn, info, error, debug

import os, subprocess, sys, time

# Wait this many seconds for the init system to finish bringing up services.
STARTUP_WAIT_SECONDS = 2 * 60


def mean(seq):
    if len(seq) == 0:
        raise ValueError("Cannot calculate mean of empty sequence.")
    return sum(seq) / float(len(seq))


class ManifestManager(object):
    """Data structure for working with the manifest file"""

    NUM_MAILS_BYTES = 4  # number of bytes used for the (ASCII) field
    NUM_MAILS_FMT = "%%0%dd" % NUM_MAILS_BYTES

    NUM_REBOOTS_BYTES = 8
    NUM_REBOOTS_FMT = "%%0%dd" % NUM_REBOOTS_BYTES

    # Start temperature stored in-manifest as YYYYY.ZZ
    START_TEMPERATURE_BYTES = 8
    START_TEMPERATURE_FMT = "%08.2f"

    # Mandatory manifest header fields (others exist, e.g. start temperatures)
    HEADER_FIELDS = set(["num_reboots", "eta_avail_idx", "num_mails_sent"])

    def __init__(self, config, platform, new_file=False):
        """If new_file is True, write a new manifest file to disk based on the
        contents of the config file, otherwise parse the (existing) manifest
        file corresponding with the config file."""

        self.platform = platform

        # Maximum values for mutible header fields
        self.num_mails_maxout = 10 ** ManifestManager.NUM_MAILS_BYTES - 1
        self.num_reboots_maxout = 10 ** ManifestManager.NUM_REBOOTS_BYTES - 1

        self.path = ManifestManager.get_filename(config)
        if new_file:
            self._write_new_manifest(config)
        self._parse()

    @staticmethod
    def get_filename(config):
        assert config.filename.endswith(".krun")
        config_base = config.filename[:-5]
        return config_base + ".manifest"

    def _reset(self):
        # All populated in _parse()
        #
        # Do not directly mutate these fields. Use the mutator methods below to
        # ensure the on-disk manifest file is in sync with the in-memory
        # instance.
        self.next_exec_key = None
        self.next_exec_idx = -1
        self.next_exec_flag_offset = None
        self.num_execs_left = 0
        self.total_num_execs = 0
        self.eta_avail_idx = 0
        self.num_mails_sent = 0
        self.num_mails_sent_offset = None
        self.outstanding_exec_counts = {}
        self.completed_exec_counts = {}  # including errors
        self.skipped_keys = set()
        self.non_skipped_keys = set()
        self.num_reboots = -1
        self.num_reboots_offset = None
        self.starting_temperatures = {} # name -> (offset, degrees C floats)

    def _open(self):
        debug("Reading status cookie from %s" % self.path)
        return open(self.path, "r+")

    # In its own method, as it needs a config instance
    def get_total_in_proc_iters(self, config):
        num = 0
        for key, exec_count in self.outstanding_exec_counts.iteritems():
            _, vm, _ = key.split(":")
            vm_num_iters = config.VMS[vm]["n_iterations"]
            num += vm_num_iters * exec_count

        return num

    def _parse(self):
        self._reset()
        fh = self._open()
        offset = 0
        seen_headers = set()

        # Parse manifest header
        for line in fh:
            strip_line = line.strip()
            if strip_line == "keys":
                offset += len(line)
                break
            else:
                key, val = strip_line.split("=")
                if key == "eta_avail_idx":
                    self.eta_avail_idx = int(val)
                elif key == "num_mails_sent":
                    self.num_mails_sent = int(val)
                    self.num_mails_sent_offset = offset + len(key) + 1  # +1 to skip '='
                elif key == "num_reboots":
                    self.num_reboots = int(val)
                    self.num_reboots_offset = offset + len(key) + 1
                elif key.startswith("start_temp_"):
                    sensor_name = key[len("start_temp_"):]
                    assert sensor_name in self.platform.temp_sensors
                    self.starting_temperatures[sensor_name] = \
                        offset + len(key) + 1, float(val)
                else:
                    util.fatal("bad key in the manifest header: %s" % key)
                seen_headers.add(key)
                offset += len(line)
        else:
            assert False

        # Check we saw all the necessary header fields
        assert ManifestManager.HEADER_FIELDS.issubset(seen_headers)

        # Get info from the rest of the file
        exec_idx = 0
        for line in fh:
            flag, key = line.strip().split(" ")
            if key not in self.outstanding_exec_counts:
                self.outstanding_exec_counts[key] = 0
            if not key in self.completed_exec_counts:
                self.completed_exec_counts[key] = 0

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

            if flag != "S":
                self.non_skipped_keys |= set([key])
                self.total_num_execs += 1
            else:
                self.skipped_keys |= set([key])

            if flag in ["E", "C"]:
                self.completed_exec_counts[key] += 1

            exec_idx += 1
            offset += len(line)
        fh.close()

    def update_num_mails_sent(self):
        """Increments the num_mails_sent_counter in the manifest file"""

        debug("Update num_mails_sent in manifest: %s -> %s" %
              (self.num_mails_sent, self.num_mails_sent + 1))
        fh = self._open()
        fh.seek(self.num_mails_sent_offset)
        new_val = self.num_mails_sent + 1
        assert 0 <= new_val <= self.num_mails_maxout
        fh.write(ManifestManager.NUM_MAILS_FMT % (new_val))
        fh.close()

        self._reset()
        self._parse()  # update stats

    def update_num_reboots(self):
        """Updates the reboot count header in the manifest file."""

        debug("Increment reboot count in manifest")
        fh = self._open()
        fh.seek(self.num_reboots_offset)
        new_val = self.num_reboots + 1
        assert 0 <= new_val <= self.num_reboots_maxout
        fh.write(ManifestManager.NUM_REBOOTS_FMT % (new_val))
        fh.close()

        self._reset()
        self._parse()  # update stats

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

    def set_starting_temperatures(self, dct):
        """Set starting temperatures in manifest header"""

        fh = self._open()
        for sensor, val in dct.iteritems():
            offset, cur_tmp = self.starting_temperatures[sensor]
            assert cur_tmp == 0.0  # shouldn't have been written yet
            fh.seek(offset)
            fh.write(ManifestManager.START_TEMPERATURE_FMT % val)
        fh.close()

    def __eq__(self, other):
        return (self.next_exec_key == other.next_exec_key and
                self.next_exec_idx == other.next_exec_idx and
                self.next_exec_flag_offset == other.next_exec_flag_offset and
                self.num_execs_left == other.num_execs_left and
                self.total_num_execs == other.total_num_execs and
                self.eta_avail_idx == other.eta_avail_idx and
                self.outstanding_exec_counts == other.outstanding_exec_counts and
                self.skipped_keys == other.skipped_keys and
                self.non_skipped_keys == other.non_skipped_keys and
                self.starting_temperatures == other.starting_temperatures)

    def _write_new_manifest(self, config):
        """Makes the initial manifest file from the config"""

        manifest = []

        one_exec_scheduled = False
        eta_avail_idx = -1
        for exec_n in xrange(config.N_EXECUTIONS):
            for vm_name, vm_info in config.VMS.items():
                for bmark, param in config.BENCHMARKS.items():
                    for variant in vm_info["variants"]:
                        key = "%s:%s:%s" % (bmark, vm_name, variant)
                        if not config.should_skip(key):
                            manifest.append("O " + key)
                            if one_exec_scheduled and eta_avail_idx == -1:
                                # first job of second executions eta becomes known.
                                eta_avail_idx = len(manifest) - 1
                        else:
                            manifest.append("S " + key)
                            if not one_exec_scheduled:
                                debug("%s is in skip list. Not scheduling." %
                                      key)
            one_exec_scheduled = True
        debug("Writing manifest to %s" % self.path)

        # These fields are strictly fixed size, as they are mutated in-place
        num_mails_str = ManifestManager.NUM_MAILS_FMT % 0
        num_reboots_str = ManifestManager.NUM_REBOOTS_FMT % 0
        start_temperature_str = ManifestManager.START_TEMPERATURE_FMT % 0

        with open(self.path, "w") as fh:
            fh.write("eta_avail_idx=%s\n" % eta_avail_idx)
            fh.write("num_mails_sent=%s\n" % num_mails_str)
            fh.write("num_reboots=%s\n" % num_reboots_str)
            for sensor in self.platform.temp_sensors:
                fh.write("start_temp_%s=%s\n" % (sensor, start_temperature_str))
            fh.write("keys\n")
            for item in manifest:
                fh.write("%s\n" % item)


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

        self.empty_measurements = self.make_empty_measurement()

    def make_empty_measurement(self):
        """Constructs the dummy result that is used when a benchmark crashes"""

        num_cores = self.sched.platform.num_per_core_measurements
        def dummy_core_data():
            return [[] for _ in xrange(num_cores)]

        return {
            "wallclock_times": [],
            "core_cycle_counts": dummy_core_data(),
            "aperf_counts": dummy_core_data(),
            "mperf_counts": dummy_core_data(),
        }

    def __str__(self):
        return self.key

    __repr__ = __str__

    def __eq__(self, other):
        return (self.sched == other.sched and
                self.key == other.key and
                self.parameter == other.parameter)

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

        stdout, stderr, rc, envlog_filename = vm_def.run_exec(
            entry_point, self.benchmark, in_proc_iters,
            self.parameter, heap_limit_kb, stack_limit_kb)

        if not dry_run:
            try:
                measurements = util.check_and_parse_execution_results(
                    stdout, stderr, rc)
                flag = "C"
            except util.ExecutionFailed as e:
                util.log_and_mail(mailer, error, "Benchmark failure: %s" %
                                  self.key, e.message,
                                  manifest=self.sched.manifest)
                measurements = self.empty_measurements
                flag = "E"

            if vm_def.instrument:
                if flag != "E":
                    instr_data = vm_def.get_instr_data()
                    for k, v in instr_data.iteritems():
                        assert len(instr_data[k]) == in_proc_iters
                else:
                    # The benchmark failed, so we assume the instrumentation
                    # data to be compromised, and thus discard it.
                    instr_data = {}
            else:
                instr_data = {}
        else:
            measurements = self.empty_measurements
            instr_data = {}
            flag = "C"

        # We print the status *after* benchmarking, so that I/O cannot be
        # committed during benchmarking. In production, we will be rebooting
        # before the next execution, so we are grand.
        info("Finished '%s(%d)' (%s variant) under '%s'" %
             (self.benchmark, self.parameter, self.variant, self.vm_name))

        # Move the environment log out of /tmp
        if not dry_run:
            key_exec_num = self.sched.manifest.completed_exec_counts[self.key]
            util.stash_envlog(envlog_filename, self.sched.config,
                              self.sched.platform, self.key, key_exec_num)

        assert flag is not None
        return measurements, instr_data, flag


class ExecutionScheduler(object):
    """Represents our entire benchmarking session"""

    def __init__(self, config, mailer, platform, dry_run=False,
                 on_first_invocation=False):
        self.mailer = mailer

        self.config = config
        self.eta_avail = 0
        self.platform = platform
        self.on_first_invocation = on_first_invocation
        self.dry_run = dry_run
        self.log_path = self.config.log_filename(not self.on_first_invocation)

        if on_first_invocation:
            self.manifest = ManifestManager(config, platform, new_file=True)
        else:
            self.manifest = ManifestManager(self.config, platform)

    def get_estimated_exec_duration(self, results, key):
        previous_exec_times = results.eta_estimates.get(key)
        if previous_exec_times:
            return mean(previous_exec_times)
        else:
            return None # we don't know

    def get_estimated_overall_duration(self, results):
        secs = 0
        for key, num_execs in self.manifest.outstanding_exec_counts.iteritems():
            per_exec = self.get_estimated_exec_duration(results, key)
            if per_exec is not None:
                secs += self.get_estimated_exec_duration(results, key) * num_execs
            elif key in self.manifest.skipped_keys:
                continue
            else:
                return None  # Unknown time for a key which is not skipped.
        return secs

    def get_exec_estimate_time_formatter(self, results, key):
        return TimeEstimateFormatter(self.get_estimated_exec_duration(results, key))

    def get_overall_time_estimate_formatter(self, results):
        return TimeEstimateFormatter(self.get_estimated_overall_duration(results))

    def add_eta_info(self, results, key, exec_time):
        results.eta_estimates[key].append(exec_time)

    def _make_post_cmd_env(self, results):
        """Prepare an environment dict for post execution hooks"""

        jobs_until_eta_known = self.manifest.eta_avail_idx - \
            self.manifest.next_exec_idx
        if jobs_until_eta_known > 0:
            eta_val = "Unknown. Known in %d process executions." % \
                jobs_until_eta_known
        else:
            eta_val = self.get_overall_time_estimate_formatter(results).finish_str

        return {
            "KRUN_RESULTS_FILE": self.config.results_filename(),
            "KRUN_LOG_FILE": self.config.log_filename(resume=True),
            "KRUN_ETA_DATUM": now_str(),
            "KRUN_ETA_VALUE": eta_val,
            "KRUN_MANIFEST_FILE": self.manifest.path,
        }

    def run(self):
        """Benchmark execution starts here"""

        if self.on_first_invocation:
            util.log_and_mail(self.mailer, debug,
                              "Benchmarking started",
                              "Benchmarking started.\nLogging to %s" %
                              self.log_path,
                              bypass_limiter=True)

        # Important that the dmesg is collected after the above startup wait.
        # Otherwise we get spurious dmesg changes.
        self.platform.collect_starting_dmesg()

        # No executions, or all skipped
        if self.manifest.num_execs_left == 0:
            info("Empty schedule!")
            return

        bench, vm, variant = self.manifest.next_exec_key.split(":")
        job = ExecutionJob(self, vm, self.config.VMS[vm], bench, variant,
                           self.config.BENCHMARKS[bench])
        results = None  # loaded later

        # Run the pre-exec commands, the benchmark and the post-exec commands.
        # These are wrapped in a try/except, so that the post-exec commands
        # are always executed, even if an exception has occurred. We only
        # reboot /after/ the post-exec commands have completed.
        try:
            # Run the user's pre-process-execution commands. We can't put an
            # ETA estimate in the environment for the pre-commands as we have
            # not (and should not) load the results file into memory yet.
            #
            # It might seem tempting to move this outside the try block, to
            # ensure that post-hooks are only run if pre-hooks ran. We don't,
            # thus avoiding the case where only *part* of the pre-hooks run,
            # but the post-hooks then don't run.
            util.run_shell_cmd_list(self.config.PRE_EXECUTION_CMDS,)

            # Results should never be in memory while a benchmark runs because
            # their size (which gets large) increases over the course of the
            # benchmark session. If results were loaded, then each benchmark
            # would be subject to a different memory layout, which is not fair.
            #assert self.results is None

            # Deal with temperature sensors
            if self.on_first_invocation:
                info(("Wait %s secs to allow system to cool prior to "
                     "collecting initial temperature readings") %
                     self.config.TEMP_READ_PAUSE)
                self.platform.sleep(self.config.TEMP_READ_PAUSE)

                debug("Taking fresh initial temperature readings")
                self.platform.starting_temperatures = \
                    self.platform.take_temperature_readings()
                self.manifest.set_starting_temperatures(
                    self.platform.starting_temperatures)

                # Scaffold the results file
                results = Results(self.config, self.platform)
                results.write_to_file()

                info("Reboot prior to first execution")
                self._reboot()
            else:
                self.platform.starting_temperatures = \
                    {sensor: tup[1] for sensor, tup in
                     self.manifest.starting_temperatures.iteritems()}
                self.platform.wait_for_temperature_sensors()

            assert results is None

            # We collect rough execution times separate from real results. The
            # reason for this is that, even if a benchmark crashes it takes
            # time and we need to account for this when making estimates. A
            # crashing benchmark will give an empty list of iteration times,
            # meaning we can't use 'raw_exec_result' below for estimates.
            exec_start_time = time.time()
            measurements, instr_data, flag = job.run(self.mailer, self.dry_run)
            exec_end_time = time.time()

            # Store new measurements in memory. They will be written to disk
            # later at reboot time.
            results = Results(self.config, self.platform,
                                   results_file=self.config.results_filename())
            results.append_exec_measurements(job.key, measurements)

            # Store instrumentation data in a separate file
            if job.vm_info["vm_def"].instrument:
                key_exec_num = self.manifest.completed_exec_counts[job.key]
                util.dump_instr_json(job.key, key_exec_num, self.config, instr_data)

            eta_info = exec_end_time - exec_start_time
            if self.platform.hardware_reboots:
                # Add time taken to wait for system to come up if we are in
                # hardware-reboot mode.
                eta_info += STARTUP_WAIT_SECONDS
            self.add_eta_info(results, job.key, eta_info)
            self.manifest.update(flag)
        except Exception:
            raise
        finally:
            # Run the user's post-process-execution commands with updated
            # ETA estimates. Important that this happens *after* dumping
            # results, as the user is likely copying intermediate results to
            # another host.

            # _make_post_cmd_env() needs the results to make an ETA. If an
            # exception occurred in the above try block, there's a chance that
            # they have not have been loaded.
            if results is None:
                results = Results(self.config, self.platform,
                                       results_file=self.config.results_filename())

            results.write_to_file()
            util.run_shell_cmd_list(
                self.config.POST_EXECUTION_CMDS,
                extra_env=self._make_post_cmd_env(results)
            )

        assert results is not None
        tfmt = self.get_overall_time_estimate_formatter(results)

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

        if self.platform.check_dmesg_for_changes(self.manifest):
            results.error_flag = True

        assert self.manifest.num_execs_left >= 0
        if self.manifest.num_execs_left > 0:
            # print info about the next job
            benchmark, vm_name, variant = \
                self.manifest.next_exec_key.split(":")
            info("Next execution is '%s(%d)' (%s variant) under '%s'" %
                 (benchmark, self.config.BENCHMARKS[benchmark], variant, vm_name))

            tfmt = self.get_exec_estimate_time_formatter(results, job.key)
            info("{:<35s}: {} ({} from now)".format(
                "Estimated completion (next execution)",
                tfmt.finish_str,
                tfmt.delta_str))

            info("Reboot in preparation for next execution")
            self._reboot()  # also deals with dumping results file
        elif self.manifest.num_execs_left == 0:
            self.platform.save_power()

            info("Done: Results dumped to %s" % self.config.results_filename())
            err_msg = "Errors/warnings occurred -- read the log!"
            if results.error_flag:
                warn(err_msg)

            msg = "Session completed. Log file at: '%s'" % (self.log_path)

            if results.error_flag:
                msg += "\n\n%s" % err_msg

            msg += "\n\nDon't forget to disable Krun at boot."

            util.log_and_mail(self.mailer, info, "Benchmarks Complete", msg,
                              bypass_limiter=True)

    def _reboot(self):
        """Dump results to disk and reboot"""

        expected_reboots = self.manifest.total_num_execs
        self.manifest.update_num_reboots()
        debug("About to execute reboot: %g, expecting %g in total." %
              (self.manifest.num_reboots, expected_reboots))

        # Check for a boot loop
        if self.manifest.num_reboots > expected_reboots:
            util.fatal(("HALTING now to prevent an infinite reboot loop: " +
                        "INVARIANT num_reboots <= num_jobs violated. " +
                        "Krun was about to execute reboot number: %g. " +
                        "%g jobs have been completed, %g are left to go.") %
                       (self.manifest.num_reboots, self.manifest.next_exec_idx,
                        self.manifest.num_execs_left))
        self._do_reboot()

    def _do_reboot(self):
        """Really do the reboot, separate for testing"""

        if not self.platform.hardware_reboots:
            warn("SIMULATED: reboot (--hardware-reboots is OFF)")
            args = sys.argv
            debug("Simulated reboot with args: " + " ".join(args))
            os.execv(args[0], args)  # replace myself
            assert False  # unreachable
        else:
            subprocess.call(self.platform.get_reboot_cmd())
