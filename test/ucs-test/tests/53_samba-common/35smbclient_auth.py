#!/usr/share/ucs-test/runner python3
## desc: Check whether several parallel smbclient authentifications are possible
## roles:
##  - domaincontroller_master
##  - domaincontroller_backup
##  - domaincontroller_slave
## packages:
##  - univention-samba | univention-samba4
## exposure: careful
## tags:
##  - SKIP-UCSSCHOOL
##  - basic
##  - apptest
##  - skip_admember

import os
import random
import subprocess
import sys
import time

import atexit

import univention.config_registry
import univention.testing.strings as uts
import univention.testing.udm as udm_test
from univention.testing import utils
from univention.testing.ucs_samba import wait_for_drs_replication


class Test:

    def __init__(self):
        self.username = uts.random_username()
        self.password = uts.random_string()

        self.totalRounds = Test._get_int_env('smbauth_totalRounds', 3)
        self.amountPerRound = Test._get_int_env('smbauth_amountPerRound', 8)
        self.roundTime = Test._get_int_env('smbauth_roundTime', 6)
        print("Configured for %d times %d processes in %ds." % (
            self.totalRounds, self.amountPerRound, self.roundTime,
        ))

        self.innerDelay = Test._calculateInnerDelay(self.roundTime, self.amountPerRound)

    def main(self):
        Test.disable_home_mount()

        with udm_test.UCSTestUDM() as udm:
            udm.create_user(username=self.username, password=self.password)

            print("Waiting for DRS replication...")
            wait_for_drs_replication(f"(sAMAccountName={self.username})", attrs="objectSid")

            self.start_processes()
            self.check_processes()

    def start_processes(self):
        print("Starting parallel authentication...")
        for index in range(self.totalRounds):
            print("Round %d..." % (index,))
            self.smbclient()

    def smbclient(self):
        print("Forking %d processes..." % (len(self.innerDelay),))
        cmd = ("/usr/bin/smbclient", f"-U{self.username}%{self.password}", "//localhost/netlogon")
        with open(os.path.devnull, 'wb') as null:
            for delay in self.innerDelay:
                subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=null, stderr=null)
                time.sleep(delay)

    def check_processes(self):
        expectedResult = self.amountPerRound * self.totalRounds
        result = Test.checkResult(expectedResult)
        print(f"{result} of {expectedResult} have been successful.")
        if result == expectedResult:
            sys.exit(0)
        else:
            utils.fail()

    @staticmethod
    def checkResult(expectedResult, max_wait=30):
        for i in range(max_wait):
            proc = subprocess.Popen(('smbstatus',), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            count = len([line for line in proc.stdout if line.startswith(b'netlogon')])
            if count == expectedResult:
                return count
            print("%d: %d < %d" % (i, count, expectedResult))
            time.sleep(1)
        return count

    @staticmethod
    def _get_int_env(key, default):
        try:
            return int(os.getenv(key))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _calculateInnerDelay(roundTime, amountPerRound):
        """Return array of <amountPerRound> floats which sum-up to <roundTime>."""
        delayArray = [random.randrange(1, 1000, 1) for _ in range(amountPerRound)]
        total = sum(delayArray)
        delayArray = [float(_) / total * roundTime for _ in delayArray]
        return delayArray

    @staticmethod
    def disable_home_mount():
        ucr = univention.config_registry.ConfigRegistry()
        ucr.load()
        homedir_mount = ucr.get("homedir/mount")
        univention.config_registry.handler_set(['homedir/mount=false'])
        atexit.register(Test._cleanup, homedir_mount)

    @staticmethod
    def _cleanup(homedir_mount):
        if not homedir_mount:
            univention.config_registry.handler_unset(['homedir/mount'])
        else:
            univention.config_registry.handler_set([f'homedir/mount={homedir_mount}'])


if __name__ == "__main__":
    Test().main()
