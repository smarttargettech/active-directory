#!/usr/share/ucs-test/runner python3
## desc: Check UCR template mapping for samba/spoolss/architecture
## tags: [basic]
## roles:
##   - domaincontroller_master
##   - domaincontroller_backup
##   - domaincontroller_slave
##   - memberserver
## exposure: careful
## packages:
##   - univention-samba | univention-samba4
##   - univention-config

import os
import subprocess
import sys

import univention.config_registry
import univention.testing.ucr as ucr_test
from univention.testing import utils


def get_testparm_var(sectionname, varname):
    path_testparm = "/usr/bin/testparm"
    if not os.path.exists(path_testparm):
        utils.fail(f"ERROR: {path_testparm} missing")

    cmd = [
        path_testparm, "-slv",
        "--section-name=%s" % sectionname,
        "--parameter-name=%s" % varname]
    p1 = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True)
    (out, _err) = p1.communicate()
    return out.strip()


def check_spoolss_architecture(expected_value):
    spoolss_architecture = get_testparm_var("global", "spoolss: architecture")
    if spoolss_architecture.decode('UTF-8') != expected_value:
        utils.fail(f"Wrong value for samba option 'spoolss: architecture', expected '{expected_value}', got '{spoolss_architecture}'")
    else:
        print(f"Ok, samba option 'spoolss: architecture' is set to '{expected_value}'")


def host_architecture():
    if sys.maxsize > 2**32:
        return "x64"
    else:
        return "x32"


expected_spoolss_architecture = {
    "x32": "Windows NT x86",
    "x64": "Windows x64",
}


def test_run(ucr, arch):
    ucr_var = "samba/spoolss/architecture"

    ucr.load()
    previous_value = ucr.get(ucr_var)

    if arch is None:
        expected_value = expected_spoolss_architecture[host_architecture()]
        if previous_value:
            univention.config_registry.handler_unset([ucr_var])
    else:
        expected_value = expected_spoolss_architecture[arch]
        if previous_value != expected_value:
            keyval = f"{ucr_var}={expected_value}"
            univention.config_registry.handler_set([keyval])

    check_spoolss_architecture(expected_value)


if __name__ == '__main__':
    with ucr_test.UCSTestConfigRegistry() as ucr:
        test_run(ucr, None)
        test_run(ucr, "x32")
        test_run(ucr, "x64")
