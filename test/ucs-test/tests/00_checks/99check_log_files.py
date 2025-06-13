#!/usr/share/ucs-test/runner python3
## desc: Check installation log files for errors, warnings and tracebacks
## bugs: [30751, 36160, 36902]
## tags: [basic, SKIP]
## exposure: safe
## versions:
##  3.0-0: skip
##  4.0-0: fixed

import gzip
import re
import sys
from os import path

from check_log_files_definitions import Errors, Tracebacks, Warnings

from univention.management.console.modules.setup.setup_script import Profile
from univention.testing import utils
from univention.testing.codes import Reason


class CheckLogFiles:

    def __init__(self):
        """Test constructor"""
        self.errors = Errors()
        self.warnings = Warnings()
        self.tracebacks = Tracebacks()

        self.log_file = ''
        self.line_counter = 0

        self.max_trace_lines = 40  # max length of a trace in lines
        self.last_trace_msg = ''

        self.return_code = Reason.OKAY  # returned if no errors found

    def extract_traceback_message(self):
        """
        Incorporates the traceback message into one string and returns it.
        Max length of traceback defined by 'self.max_trace_lines'.
        """
        trace_message = ''
        last_line = ''

        for trace_line, line in enumerate(self.log_file, 1):
            line = line.decode('UTF-8', 'replace')
            trace_message += line
            self.line_counter += 1

            if trace_line >= self.max_trace_lines or 'Error: ' in line:
                last_line = line.strip()
                # break loop if the trace is too big or
                # if last trace line with error name was found
                break

        if trace_message not in self.last_trace_msg:
            self.last_trace_msg = trace_message
            return trace_message
        else:
            return 'Last Traceback "%s" repeats one more time.\n' % last_line

    def check_for_tracebacks(self, line, errors, msg):
        """
        Looks for the signs of a traceback in a 'line'.
        Extracts the traceback message and appends it to the
        output 'errors' with a given 'msg' in the beginning.
        """
        if self.tracebacks.wanted(line):
            errors.append(msg + '\n' + self.extract_traceback_message())
            return errors

        return errors

    def check_extra_lines(self, previous_line, pre_previous_line, definition):
        """
        Looks through the given previous and pre_previous lines to check if
        a 'failed.' message can be ignored. Returns True if so.
        """
        if (definition.ignore_extra(previous_line) and definition.ignore_extra(pre_previous_line)):
            return True

    def check_line(self, line, previous_line, pre_previous_line, definition, result, msg):
        """
        Checks a single 'line' against patterns from 'definition' and
        adds message 'msg' to list 'result' if pattern is in 'wanted'.
        Ignores the patterns matching 'ignore'. Returns 'result'.
        Checks an extra case if line == 'failed.'
        """
        if definition.ignore(line):
            return result

        if definition.wanted(line):
            if line == 'failed.':  # special case, Bug #36160
                if self.check_extra_lines(previous_line, pre_previous_line, definition):
                    return result  # ignore the 'failed.' message

            result.append(msg)
            return result

        return result

    def check_log_file(self, filename):
        """
        Checks file 'filename' for issues, returns 2-tuple (warnings, errors).
        Tracebacks would also be included to 'Errors'.
        """
        errors = []
        warnings = []
        self.line_counter = 0
        pre_previous_line = ''  # the line before the 'previous_line'
        previous_line = ''

        if not path.isfile(filename):
            print("\nThe file '%s' cannot be found, skipping..." % filename)
            return (None, None)

        basename = path.basename(filename)

        try:
            if basename.endswith('.gz'):
                self.log_file = gzip.open(filename, "rb")
            else:
                self.log_file = open(filename, "rb")

            for line in self.log_file:
                self.line_counter += 1
                line = line.decode('UTF-8', 'replace').strip()

                msg = f"{basename}:{self.line_counter}, {line}"
                errors = self.check_for_tracebacks(line, errors, msg)

                # skip the message if it is repeated from the previous line:
                if line != previous_line:
                    errors = self.check_line(line, previous_line, pre_previous_line, self.errors, errors, msg)
                    warnings = self.check_line(line, previous_line, pre_previous_line, self.warnings, warnings, msg)

                pre_previous_line = previous_line
                previous_line = line

            self.log_file.close()
        except (OSError, ValueError) as exc:
            utils.fail("An exception while working with a log file '%s': '%s'"
                       % (filename, exc))
        return (errors, warnings)

    def extend_log_ignore_definitions(self):
        """
        Changes log definitions to ignore join related errors
        (case when joinscripts are not called and thus errors appear)
        """
        join_errors = [
            '.*: Failed to load license information: .*',
            '.*Usage: /etc/init.d/slapd {start|stop|restart|force-reload|status}.*',
            '.*invoke-rc.d: initscript slapd, action "(start|restart|crestart)" failed.*',
            '.*invoke-rc.d: initscript ntp, action "restart" failed.*',
            '.*Job for univention-management-console-server.service failed.*',
            '.*Job for univention-directory-notifier.service failed.*',
            '.*Job for slapd.service failed.*',
            '.*Job for named.service failed.*',
            '.*Restarting slapd (via systemctl): slapd.service.*',
            '.*invoke-rc.d: initscript univention-management-console-server, action "reload" failed.*',
            '.*invoke-rc.d: initscript named, action "restart" failed.*',
            '.*Starting univention-directory-notifier (via systemctl).*',
            '.*rsync: .* write error: Broken pipe.*',
            'WARNING: skipped disk-usage-test as requested',
            'ch.* failed to get attributes of .*/etc/resolv.conf.* No such file or directory']

        join_warnings = [
            '.*Join script execution has been disabled via call_master_joinscripts.*',
            '.*To enable saslauthd, edit /etc/default/saslauthd and set START=yes.*']

        # adding warnings and errors caused by absence of
        # join procedure to the ignore lists
        self.errors = Errors(ignore=join_errors)
        self.warnings = Warnings(ignore=join_warnings)

    def check_installation_profile(self):
        """
        Looks for the 'call_master_joinscripts' in the
        '/etc/univention/installation_profile' to ignore the join
        related errors in case setting is 'false'.
        """
        InstallProfile = Profile()
        try:
            InstallProfile.load(filename='/etc/univention/installation_profile')
            if bool(re.match('false', InstallProfile.get_list('call_master_joinscripts')[0], re.IGNORECASE)):
                print("\nThe 'call_master_joinscripts' is 'false' in "
                      "'/etc/univention/installation_profile', adjusting "
                      "patterns to ignore respective 'join' messages.")
                self.extend_log_ignore_definitions()
        except (OSError, IndexError) as exc:
            print("\nAn error occurred while trying to check the installation "
                  "profile for 'call_master_joinscripts' setting: %r "
                  "Adjusting patterns to ignore respective 'join' messages."
                  % exc)
            self.extend_log_ignore_definitions()

    def main(self, log_files):
        """
        Looks for Errors, Tracebacks and Warnings in the given list of
        'log_files'. Test fails if Errors (or/and Tracebacks) were found.
        Test passes if only warnings were found.
        """
        self.check_installation_profile()

        for filename in log_files:
            errors, warnings = self.check_log_file(filename)

            if errors:
                # Errors detected, test should fail
                self.return_code = Reason.FAIL
                print("\nErrors found in '%s':\n" % filename)
                for line in errors:
                    print(" E: %s" % line)

            if warnings:
                print("\nWarnings found in '%s':\n" % filename)
                for line in warnings:
                    print(" W: %s" % line)


if __name__ == '__main__':
    log_files = ("/var/log/univention/installation.log",
                 "/var/log/univention/installation.log.gz",
                 "/var/log/univention/installer.log",
                 "/var/log/univention/installer.log.gz",
                 "/var/log/univention/updater.log",
                 "/var/log/univention/actualise.log",
                 "/var/log/univention/join.log",
                 "/var/log/univention/listener.log",
                 "/var/log/univention/setup.log")

    LogChecker = CheckLogFiles()
    LogChecker.main(log_files)

    sys.exit(int(LogChecker.return_code))
