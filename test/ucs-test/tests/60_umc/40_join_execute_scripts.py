#!/usr/share/ucs-test/runner python3
## desc: Test the UMC domain join module
## bugs: [34624]
## roles:
##  - domaincontroller_backup
##  - domaincontroller_slave
##  - memberserver
## exposure: dangerous
## versions:
##  4.0-2: skip

import os
import sys

from univention.testing import utils

from umc import JoinModule


class TestUMCDomainJoinModule(JoinModule):

    def link_join_script(self, script_name, path):
        """
        Creates a symblic link to a script with provided 'script_name' on
        the provided 'path'. Assuming script is in the same path as the
        test itself. Returns missing software code if cannot find the test
        join script with the 'script_name'.
        """
        try:
            if os.path.isfile(script_name):
                if not os.path.exists(path):
                    os.symlink(os.path.abspath(script_name), path)
            else:
                print("Missing file with the provided name '%s' on path '%s'" % (script_name, path))
                self.return_code_result_skip()
        except OSError as exc:
            utils.fail("Failed to create a symbolic link to the '%s' on the path '%s' or check if '%s' exists. Exception: '%s'" % (script_name, path, script_name, exc))

    def remove_join_script_link(self, path):
        """
        Removes the symbolic link to a script located at provided 'path'
        Checks if path exists.
        """
        try:
            if os.path.exists(path):
                os.unlink(path)
            else:
                print("The provided path '%s' does not exist, no links were removed" % path)
        except OSError as exc:
            utils.fail("Failed to remove a symbolic link to the test join script, or failed to check if '%s' exists. Exception: '%s'" % (path, exc))

    def get_join_script_state(self, script_name):
        """
        Makes a query request for all join scripts and returns the
        value of the 'configured' field for the given 'script_name'
        """
        join_scripts = self.query_joinscripts()
        for script in join_scripts:
            if script.get('script') == script_name:
                return script.get('configured')

    def execute_pending_scripts(self):
        """
        Executes all scripts that are pending by first querying
        for scripts that are pending and than making a single UMC
        request to execute them.
        """
        script_names = []
        for script in self.query_joinscripts():
            if not script.get('configured'):
                script_names.append(script.get('script'))
        self.run(script_names=script_names)

    def main(self):
        """A method to test the UMC domain join module"""
        self.create_connection_authenticate()

        test_script = '99univention-test-join-script'
        test_script_state = None
        script_link_path = '/usr/lib/univention-install/'
        join_status_file = '/var/univention-join/status'

        try:
            print("Saving a backup of initial join status file '%s'" % join_status_file)
            self.copy_file(join_status_file, join_status_file + '.bak')

            print("Creating a symbolic link to the test join script '%s' in the '%s'" % (test_script, script_link_path))
            self.link_join_script(test_script + '.inst', script_link_path + test_script + '.inst')
            self.wait_rejoin_to_complete(5)  # check running state and wait
            test_script_state = self.get_join_script_state(test_script)
            if test_script_state:
                utils.fail("The state of the join script '%s' is 'configured' right after script link was created in the join scripts folder '%s'" % (test_script, script_link_path))

            # case 1: execute single join script
            print("Executing test join script '%s' via UMC request" % test_script)
            self.run(script_names=[test_script])
            self.wait_rejoin_to_complete(5)  # check running state and wait
            test_script_state = self.get_join_script_state(test_script)
            if not test_script_state:
                utils.fail("The state of the join script '%s' 'configured' is '%s' after the script was executed" % (test_script, test_script_state))

            # case 2: executing single join script with 'Force' and with
            # restoration of the status file prior to execution
            print("Force executing test join script '%s' via UMC request" % test_script)
            self.copy_file(join_status_file + '.bak', join_status_file)
            self.run(script_names=[test_script], force=True)
            self.wait_rejoin_to_complete(5)  # check running state and wait
            test_script_state = self.get_join_script_state(test_script)
            if not test_script_state:
                utils.fail("The state of the join script '%s' 'configured' is '%s' after the script was force executed" % (test_script, test_script_state))

            # case 3: creating more test join scripts with links
            # and executing all pending scripts after
            print("Creating two more test join scripts, linking them and executing all pending scripts")
            self.copy_file(test_script + '.inst', test_script + '_copy1.inst')
            self.copy_file(test_script + '.inst', test_script + '_copy2.inst')
            self.link_join_script(test_script + '_copy1.inst', script_link_path + test_script + '_copy1.inst')
            self.link_join_script(test_script + '_copy2.inst', script_link_path + test_script + '_copy2.inst')
            self.execute_pending_scripts()
            self.wait_rejoin_to_complete(5)  # check running state and wait
            test_script_state = self.get_join_script_state(test_script + '_copy1')
            if not test_script_state:
                utils.fail("The state of the join script '%s' 'configured' is '%s' after all pending scripts were executed" % (test_script + '_copy1', test_script_state))
            test_script_state = self.get_join_script_state(test_script + '_copy2')
            if not test_script_state:
                utils.fail("The state of the join script '%s' 'configured' is '%s' after all pending scripts were executed" % (test_script + '_copy2', test_script_state))
        finally:
            print("\nRemoving all links and test script copies, restoring status file")
            # Unlinking all join scripts:
            self.remove_join_script_link(script_link_path + test_script + '.inst')
            self.remove_join_script_link(script_link_path + test_script + '_copy1.inst')
            self.remove_join_script_link(script_link_path + test_script + '_copy2.inst')
            # Deleting test join script copies:
            self.delete_file(test_script + '_copy1.inst')
            self.delete_file(test_script + '_copy2.inst')

            # Overwriting status file from backup and removing backup:
            self.copy_file(join_status_file + '.bak', join_status_file)
            self.delete_file(join_status_file + '.bak')


if __name__ == '__main__':
    TestUMC = TestUMCDomainJoinModule()
    sys.exit(TestUMC.main())
