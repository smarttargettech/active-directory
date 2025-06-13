#!/usr/share/ucs-test/runner pytest-3 -s -vvv
## desc: Check if additional routes can be set for interfaces
## roles:
##  - domaincontroller_master
##  - domaincontroller_backup
##  - domaincontroller_slave
##  - memberserver
## tags:
##  - basic
##  - apptest
## exposure: dangerous

import re
import subprocess
import time

import univention.testing.ucr as ucr_test
from univention.testing import utils


def _check_route(route, interface, gateway) -> bool:
    print()
    for line in subprocess.check_output(['/usr/sbin/ip', 'route']).decode().splitlines():
        print(line)
        if line.startswith(route) and f'dev {interface}' in line and f'via {gateway}' in line:
            return True
    return False


def test_additional_route_for_interface():
    with ucr_test.UCSTestConfigRegistry() as ucr:
        re_var = re.compile(r'^interfaces/([^/]+)/address$')
        interface = None
        for key in ucr:
            match = re_var.match(key)
            if match:
                interface = match.group(1)
                break
        gateway = ucr.get('gateway')
        assert gateway.strip(), 'No gateway found'
        assert interface, 'No interface found'
        print(f'Using interface "{interface}" and gateway "{gateway}" for testing...')

        print('>>>>> setting UCR variable')

        # add route
        ucr.handler_set([f"interfaces/{interface}/route/UCSTESTROUTE=net 10.254.254.0 netmask 255.255.255.0 gw {gateway}"])
        found = False
        i = 30
        while i > 0 and not found:
            i -= 1
            time.sleep(1)
            found = _check_route('10.254.254.0/24', interface, gateway)
        if not found:
            utils.fail("Route not found after 30 attempts")

        print('>>>>> route has been set successfully')
        print('>>>>> removing UCR variable')

        # remove route
        ucr.handler_unset([f'interfaces/{interface}/route/UCSTESTROUTE'])
        i = 30
        found = True
        while i > 0 and found:
            i -= 1
            time.sleep(1)
            found = _check_route('10.254.254.0/24', interface, gateway)
        if found:
            utils.fail("Route has not been removed after 30 attempts")

        print('>>>>> route has been removed successfully')
