#!/usr/share/ucs-test/runner python3
## desc: Permissions after renewing ssl certificate
## versions:
##  3.2-4: skip
## tags: [apptest]
## roles-not: []
## exposure: dangerous
## bugs: [36557, 31941, 34082, 34080, 32988]

import glob
import grp
import os
import pwd
import stat

import univention.testing.ucr as ucr_test
from univention.testing import utils


UNIVENTION_DIR = '/etc/univention'
SSLDIR = '/etc/univention/ssl'
SKIP = '/etc/univention/ssl/unassigned-hostname.unassigned-domain'


def get_computers():
    with ucr_test.UCSTestConfigRegistry() as ucr:
        files_path = glob.glob('/etc/univention/ssl/*%s' % ucr.get('domainname'))
        return [os.path.basename(x) for x in files_path]


def get_host_cert_dir(hostname):
    with ucr_test.UCSTestConfigRegistry() as ucr:
        return '/etc/univention/ssl/%s.%s' % (hostname, ucr.get('domainname'))


def get_dir_files(dir_path, recursive=False):
    result = []
    for f in glob.glob('%s/*' % dir_path):
        if os.path.isfile(f):
            result.append(f)
        if os.path.isdir(f) and recursive:
            # TODO: remove line 60 after fixing Bug #36557
            if f != SKIP:
                result.extend(get_dir_files(f))
    return result


def get_owner(file_path):
    st = os.stat(file_path)
    return pwd.getpwuid(st.st_uid)[0]


def is_owned_by(file_path, owner):
    st = os.stat(file_path)
    return pwd.getpwuid(st.st_uid)[0] == owner


def is_user_readable(file_path, username):
    st = os.stat(file_path)
    if pwd.getpwuid(st.st_uid)[0] == username:
        return bool(st.st_mode & stat.S_IRUSR)
    else:
        return bool(st.st_mode & stat.S_IROTH)


def is_user_writable(file_path, username):
    st = os.stat(file_path)
    if pwd.getpwuid(st.st_uid)[0] == username:
        return bool(st.st_mode & stat.S_IWUSR)
    else:
        return bool(st.st_mode & stat.S_IWOTH)


def is_group_readable(file_path, group_name):
    st = os.stat(file_path)
    if grp.getgrgid(st.st_gid)[0] == group_name:
        return bool(st.st_mode & stat.S_IRGRP)
    else:
        return bool(st.st_mode & stat.S_IROTH)


def is_group_writable(file_path, group_name):
    st = os.stat(file_path)
    if grp.getgrgid(st.st_gid)[0] == group_name:
        return bool(st.st_mode & stat.S_IWGRP)
    else:
        return bool(st.st_mode & stat.S_IWOTH)


def is_others_readable(file_path):
    st = os.stat(file_path)
    return bool(st.st_mode & stat.S_IROTH)


def is_others_writable(file_path):
    st = os.stat(file_path)
    return bool(st.st_mode & stat.S_IWOTH)


def check_dc_backup_hosts_readability(ssl_files):
    for _file in ssl_files:
        if not is_group_readable(_file, 'DC Backup Hosts'):
            utils.fail('DC Backup Hosts failed to read %s' % _file)


def check_dc_backup_hosts_writability(ssl_files):
    for _file in ssl_files:
        if not is_group_writable(_file, 'DC Backup Hosts'):
            utils.fail('DC Backup Hosts failed to read %s' % _file)


def check_hosts_readability():
    for host in get_computers():
        for _file in get_dir_files(get_host_cert_dir(host), recursive=True):
            if not is_user_readable(_file, host):
                utils.fail('%s failed to read %s' % (host, _file))


def check_hosts_writability():
    for host in get_computers():
        for _file in get_dir_files(get_host_cert_dir(host), recursive=True):
            if not is_user_writable(_file, host):
                utils.fail('DC Backup Hosts can modify %s' % _file)


def is_exception(_file):
    return ('CAcert.pem' in _file or 'serial' in _file or 'index' in _file)


def check_others_writability(ssl_files):
    for _file in ssl_files:
        if is_others_writable(_file):
            utils.fail('Others can modify %s' % _file)


def check_others_readability(ssl_files):
    for _file in ssl_files:
        if is_others_readable(_file) and not is_exception(_file):
            utils.fail('Others can read %s' % _file)


def main():
    ssl_files = get_dir_files(SSLDIR, recursive=True)

    # Fails because of Bug #36557
    check_dc_backup_hosts_readability(ssl_files)
    # TODO: uncomment next line after Bug #34082 is closed
    # check_dc_backup_hosts_writability(ssl_files)
    check_hosts_readability()
    check_hosts_writability()
    check_others_readability(ssl_files)
    check_others_writability(ssl_files)


if __name__ == '__main__':
    main()
