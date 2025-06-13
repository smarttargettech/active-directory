#!/usr/share/ucs-test/runner python3
## desc: Test the UMC domain complete rejoin
## bugs: [34624]
## roles:
##  - domaincontroller_backup
##  - domaincontroller_slave
##  - memberserver
## tags: [SKIP, producttest]
## exposure: dangerous

import sys
from os import path

from univention.testing import utils

from umc import JoinModule


class TestUMCDomainRejoin(JoinModule):

    def clear_status_file(self, file_path):
        """
        Clears all contents in the status file located at the
        provided 'file_path' by opening file for writing.
        """
        File = None
        try:
            if path.exists(file_path):
                File = open(file_path, 'w')
            else:
                utils.fail("Could not find the status file at the provided file_path '%s'" % file_path)
        except OSError as exc:
            utils.fail(f"An exception while clearing the status file at '{file_path}': '{exc}'")
        finally:
            if File:
                File.close()

    def main(self):
        """A method to test the UMC domain complete rejoin"""
        self.create_connection_authenticate()
        join_status_file = '/var/univention-join/status'

        try:
            print("Saving a backup of initial join status file '%s'" % join_status_file)
            self.copy_file(join_status_file, join_status_file + '.bak')

            # clean the status file and perform a complete rejoin
            print("Clearing the status file and making a rejoin request. (This operation may take up to 20 minutes)")
            self.clear_status_file(join_status_file)
            # check that no scripts are 'configured'==True with clean status
            for result in self.query_joinscripts():
                if result.get('configured'):
                    utils.fail("The following join script '%s' was 'configured'==True while should not be" % result)
            self.join(hostname=self.ucr.get('ldap/master'))
            self.wait_rejoin_to_complete(120)
            # check that all scripts are 'configured'==True after rejoin
            for result in self.query_joinscripts():
                if not result.get('configured'):
                    utils.fail("The following join script '%s' was 'configured'==False while should be True" % result)
        finally:
            print("\nRestoring join status file from backup '.bak'")
            # Overwriting status file from backup and removing backup:
            self.copy_file(join_status_file + '.bak', join_status_file)
            self.delete_file(join_status_file + '.bak')


if __name__ == '__main__':
    TestUMC = TestUMCDomainRejoin()
    sys.exit(TestUMC.main())
