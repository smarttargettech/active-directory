#!/usr/share/ucs-test/runner python3
## desc: install all packages from a release
## roles: [domaincontroller_backup]
## tags: [producttest]
## timeout: 10800
## exposure: careful
## packages: []

import glob
import re
import subprocess


def run_command(cmd):
    """Runs cmd command in terminal"""
    print(' ** %r' % cmd)
    popen_obj = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    out, _err = popen_obj.communicate()
    ret = popen_obj.returncode
    if ret != 0:
        print(f'Return code = {ret},\nOut= {out}')
        return 1


def apt_update():
    """Performs apt-get update"""
    cmd = ['apt-get', 'update']
    return run_command(cmd)


def test_install(pkg_name):
    """Simulate packages installation"""
    cmd = ['apt-get', '-s', 'install', pkg_name]
    return run_command(cmd)


def main():
    if not apt_update():
        files = glob.glob('/var/lib/apt/lists/*Packages')
        broken_pkgs = []
        for filename in files:
            with open(filename) as f:
                pkgs_list = re.findall(
                    re.compile(r'Package: (.*)\n'),
                    f.read(),
                )
                for pkg in pkgs_list:
                    if test_install(pkg):
                        broken_pkgs.append(pkg)
        if broken_pkgs:
            print('Broken Packages:', broken_pkgs)
            return 1
    else:
        print('apt-get update failed')
        return 1


if __name__ == '__main__':
    main()
