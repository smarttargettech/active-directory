#!/usr/share/ucs-test/runner python3
## desc: Check if a s4 loop is present after running all the tests
## roles:
##  - domaincontroller_master
## packages:
##  - univention-s4-connector
## bugs:
##  - 52358
## exposure: safe

import subprocess
import time

import univention.s4connector.s4
from univention.config_registry import ConfigRegistry, handler_set as ucr_set
from univention.testing.utils import LDAPReplicationFailed, fail, wait_for_replication_and_postrun


ucr = ConfigRegistry()
ucr.load()


def get_rejected():
    s4 = univention.s4connector.s4.s4.main(ucr, 'connector')
    rejected = []
    for (_filename, dn) in s4.list_rejected():
        rejected.append(dn)
    for (_filename, dn) in s4.list_rejected_ucs():
        rejected.append(dn)
    return rejected


def read_connector_log():
    f = open('/var/log/univention/connector-s4.log')
    return f.read().splitlines()


def count_connector_log_lines():
    with open('/var/log/univention/connector-s4.log') as f:
        return len(f.readlines())


def looping_objects(log):
    rejected = get_rejected()
    cleaned_log = []
    for i in log:
        if "sync AD > UCS" in i or 'sync UCS > AD' in i:
            i = i.rsplit(']', 1)[1].strip(" '").lower()
            if i not in cleaned_log and i not in rejected:
                cleaned_log.append(i)
    return cleaned_log


def check_if_looping():
    lines_before = count_connector_log_lines()
    try:
        wait_for_replication_and_postrun()
    except LDAPReplicationFailed:
        # find the objects that are still modified, even though all we did was waiting
        lines_after = count_connector_log_lines()
        diff = lines_after - lines_before
        log = read_connector_log()
        loops = looping_objects(log[-diff:])
        print('#######################################################')
        print('ERROR: Looping Objects detected:')
        print('#######################################################')
        print('\n'.join(loops))
        print('#######################################################')

        print('ERROR: postrun never ran, ldap replication failed, most likely because of an s4con loop. Stopping the loop')
        # setting syncmode to read to stop the loop
        sync_mode = ucr.get('connector/s4/mapping/syncmode', 'sync')

        try:
            ucr_set(['connector/s4/mapping/syncmode=read'])
            subprocess.check_call(["service", "univention-s4-connector", "restart"])
            # wait a bit to calm down the connector ..
            time.sleep(5)
        finally:
            ucr_set(['connector/s4/mapping/syncmode=%s' % sync_mode])
            subprocess.check_call(["service", "univention-s4-connector", "restart"])
            print('Trying to wait for postrun again, see if a loop was the reason for failure')
            # wait a bit for things to settle..
            try:
                wait_for_replication_and_postrun()
            except LDAPReplicationFailed:
                fail('Test failed likely to different reason than an s4con-loop')
            else:
                fail('Stopping S4-Connector synchronization helped, which means a loop was created')


def main():
    check_if_looping()


if __name__ == '__main__':
    main()
# vim: set ft=python :
