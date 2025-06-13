#!/usr/share/ucs-test/runner python3
## desc: install all packages from standard packet list
## roles: [domaincontroller_master]
## tags: [apptest]
## exposure: careful
## bugs: [36006]
## versions:
##  3.2-3: skip
## packages: []

import re
import subprocess

from univention.testing import utils


def run_command(cmd):
    """Runs cmd command in terminal"""
    print(' ** %r' % cmd)
    popen_obj = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, _err = popen_obj.communicate()
    ret = popen_obj.returncode
    if ret != 0:
        print(f'Return code = {ret},\nOut= {out}')
        return 1
    else:
        return out


def apt_update():
    """Performs apt-get update"""
    cmd = ['apt-get', 'update']
    return run_command(cmd)


def test_install(pkg_name):
    """Simulate packages installation"""
    cmd = ['apt-get', '-s', 'install', pkg_name]
    return run_command(cmd)


def get_packets_list():
    """Returns Packet list"""
    cmd = [
        'univention-ldapsearch',
        '-x',
        'univentionPackageDefinition=*',
        'univentionPackageDefinition',
    ]
    search_result = run_command(cmd)
    return re.findall(re.compile(r'univentionPackageDefinition: (\w*)\n'), search_result)


def main():
    packets = get_packets_list()
    if apt_update() != 1:
        broken_pkgs = []
        for packet in packets:
            if test_install(packet) == 1:
                broken_pkgs.append(packet)
        if broken_pkgs:
            utils.fail('Un-installable Packages: %r' % broken_pkgs)
    else:
        utils.fail('apt-get update failed')


if __name__ == '__main__':
    main()
