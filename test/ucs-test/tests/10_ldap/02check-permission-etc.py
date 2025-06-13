#!/usr/share/ucs-test/runner python3
## desc: Check for filesystem permissions on ldap.secret, ldap-backup.secret, slave-join.secret
## tags:
##  - basic
##  - apptest
## roles:
##  - domaincontroller_master
##  - domaincontroller_backup
## packages:
##  - univention-ldap-server
## exposure: safe

import grp
import os
import pwd
import stat
import sys

from univention.config_registry import ConfigRegistry


RETURN_PASS_CODE = 100
RETURN_FAIL_CODE = 110


def main():
    """A main method stores almost completely code."""
    exit_code = None  # use for exitcode of the entire test

    filenames_groups = [
        ("/etc/ldap.secret", "DC Backup Hosts"),
        ("/etc/ldap-backup.secret", "DC Backup Hosts"),
        ("/etc/slave-join.secret", "Slave Join"),
    ]  # filepaths and groupnames to check
    shouldowner = "root"

    ucr = ConfigRegistry()
    ucr.load()

    try:
        for filename, filegroup in filenames_groups:
            if not os.path.exists(filename) and filename == '/etc/slave-join.secret' and ucr.get('server/role') == 'domaincontroller_backup':
                # see https://forge.univention.org/bugzilla/show_bug.cgi?id=27662
                print('Ignore /etc/slave-join.secret on DC Backup')
                continue
            return_code = check_owner_groupname(filename, shouldowner, filegroup)
            if not return_code:
                exit_code = RETURN_FAIL_CODE
            return_code = check_permissions(filename)
            if not return_code:
                exit_code = RETURN_FAIL_CODE
    except OSError as error:
        print(f"An error occurred with: {error}", file=sys.stderr)
        sys.exit(RETURN_FAIL_CODE)

    sys.exit(exit_code)


def check_owner_groupname(filename, shouldowner, shouldgroup):
    """Checks a given file for a right owner and a right group."""
    return_code = True
    stat_info = os.stat(filename)  # statistics about a given file
    uid = stat_info.st_uid  # userid
    gid = stat_info.st_gid  # groupid
    owner = pwd.getpwuid(uid)[0]  # get username/owner
    group = grp.getgrgid(gid)[0]  # get groupname
    if owner != shouldowner:
        print(f"ERROR: '{filename}' has wrong owner '{owner}' but should be '{shouldowner}'", file=sys.stderr)
        return_code = False
    if group != shouldgroup:
        print(f"ERROR: '{filename}' has wrong group '{group}' but should be '{shouldgroup}'", file=sys.stderr)
        return_code = False
    return return_code


def check_permissions(filename):
    """Checks file permissions for -rw-r-----"""
    return_code = True
    stat_info = os.stat(filename)
    stat_info_stmode = stat_info.st_mode
    if (stat.S_IRUSR & stat_info_stmode) and (stat.S_IWUSR & stat_info_stmode) and (stat.S_IRGRP & stat_info_stmode):
        pass
    elif (stat.S_IXUSR | stat.S_IWGRP | stat.S_IXGRP | stat.S_IRWXO) & stat_info_stmode:
        print(f"ERROR: '{filename}' has wrong permissions {stat_info_stmode:04o}. Should be exactly -rw-r-----", file=sys.stderr)
        return_code = False
    else:
        print(f"ERROR: '{filename}' has wrong permissions {stat_info_stmode:04o}. Should be exactly -rw-r-----", file=sys.stderr)
        return_code = False
    return return_code


if __name__ == '__main__':
    main()
