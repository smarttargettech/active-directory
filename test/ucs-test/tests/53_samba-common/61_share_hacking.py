#!/usr/share/ucs-test/runner pytest-3 -s
## desc: Try to hack through manipulated share paths
## tags: [SKIP]
## roles:
##   - domaincontroller_master
##   - domaincontroller_backup
##   - domaincontroller_slave
##   - memberserver
## exposure: dangerous
## packages:
##   - univention-samba | univention-samba4
##   - univention-config

import contextlib
import os
import shutil
import subprocess

import ldap.dn
import pytest

import univention.testing.udm as udm_test
from univention.testing import strings, ucr as _ucr, utils


@contextlib.contextmanager
def preconditions(path):
    if path == '/home/Administrator/etc':
        os.symlink('/etc', path)
    elif path == '/home/Administrator/foo':
        os.makedirs(path)
    elif path == '/home/Administrator/bar':
        os.symlink('/etc/hosts', path)
    yield
    if path in ('/home/Administrator/etc', '/home/Administrator/bar'):
        os.unlink(path)
    elif path == '/home/Administrator/foo':
        shutil.rmtree(path)


@pytest.mark.parametrize('modify', [False, True])
@pytest.mark.parametrize('path,file_', [
    ['/etc'],
    ['/etc/'],
    ['/etc/foo/../'],
    ['../etc'],
    ['etc'],
    ['/var'],
    ['/var/'],
    ['/proc'],
    ['/dev'],
    ['/root'],
    ['/sys'],
    ['/tmp'],
    ['/home/Administrator/etc'],  # symlink to /etc
    ['/home/Administrator/foo'],  # folder containing symlink to /etc
    ['/home/Administrator/bar'],  # symlink to /etc/hosts
])
def test_filename_validation(modify, path, file_):
    def check(safe=False):
        # we have to check two cases here: samba share and NFS share
        subprocess.check_output(['smbclient', '\\\\%s.%s\\%s' % (ucr['hostname'], ucr['domainname'], name), '-U', 'Administrator%univention', '-c', 'get %s /dev/stdout' % (file_,)])
        assert name not in open('/etc/samba/shares.conf').read()

    lo = utils.get_ldap_connection()
    with udm_test.UCSTestUDM() as udm, _ucr.UCSTestConfigRegistry() as ucr, preconditions():
        pos = 'cn=shares,%s' % (udm.LDAP_BASE,)
        name = strings.random_string()
        dn = 'cn=%s,%s' % (ldap.dn.escape_dn_chars(name), pos)
        attrs = {
            'objectClass': ['univentionShareSamba', 'univentionShare', 'top', 'univentionObject', 'univentionShareNFS'],
            'cn': [name],
            'univentionShareNFSSync': ['sync'],
            'univentionShareSambaForceDirectoryMode': ['0'],
            'univentionShareWriteable': ['yes'],
            'univentionShareSambaForceSecurityMode': ['0'],
            'univentionShareSambaLocking': ['1'],
            'univentionShareSambaForceDirectorySecurityMode': ['0'],
            'univentionShareSambaMSDFS': ['no'],
            'univentionShareSambaCreateMode': ['0744'],
            'univentionShareSambaWriteable': ['yes'],
            'univentionShareSambaInheritPermissions': ['no'],
            'univentionShareSambaBrowseable': ['yes'],
            'univentionShareSambaHideUnreadable': ['no'],
            'univentionShareSambaDirectoryMode': ['0755'],
            'univentionShareSambaPublic': ['no'],
            'univentionShareSambaSecurityMode': ['0777'],
            'univentionShareDirectoryMode': ['00755'],
            'univentionShareSambaBlockingLocks': ['1'],
            'univentionSharePath': ['/home/' if modify else path],
            'univentionShareSambaDirectorySecurityMode': ['0777'],
            'univentionShareSambaLevel2Oplocks': ['1'],
            'univentionShareSambaNtAclSupport': ['1'],
            'univentionShareSambaCscPolicy': ['manual'],
            'univentionShareSambaForceCreateMode': ['0'],
            'univentionObjectType': ['shares/share'],
            'univentionShareSambaDosFilemode': ['no'],
            'univentionShareSambaOplocks': ['1'],
            'univentionShareSambaInheritAcls': ['1'],
            'univentionShareSambaFakeOplocks': ['0'],
            'univentionShareGid': ['0'],
            'univentionShareNFSRootSquash': ['yes'],
            'univentionShareUid': ['0'],
            'univentionShareSambaStrictLocking': ['Auto'],
            'univentionShareSambaName': [name],
            'univentionShareNFSSubTree': ['yes'],
            'univentionShareSambaInheritOwner': ['no'],
            'univentionShareHost': ['%(hostname)s.%(domainname)s'],
        }
        al = [(key, [v % dict(ucr) for v in val]) for key, val in attrs.items()]
        print(('Creating', dn))
        dn = lo.add(dn, al) or dn
        try:
            utils.wait_for_replication_and_postrun()
            if modify:
                check(safe=True)
                lo.modify(dn, [
                    ('univentionSharePath', '/home/', path),
                ])
                print(('Modified', dn))
                utils.wait_for_replication_and_postrun()

            check()
        finally:
            lo.delete(dn)
        utils.wait_for_replication_and_postrun()
        check()


def test_newline_nfs_hacking():
    lo = utils.get_ldap_connection()
    with udm_test.UCSTestUDM() as udm, _ucr.UCSTestConfigRegistry() as ucr:
        share = udm.create_object('shares/share', name=strings.random_string(), host='%(hostname)s.%(domainname)s' % ucr, path='/home/', wait_for_replication=False)
        lo.modify(share, [('univentionShareNFSAllowed', '', 'foo\n"/etc" -rw,root_squash,sync,subtree_check * #')])
        utils.wait_for_replication_and_postrun()
        # TODO: access /home and /etc


# def test_multiple_entries_hacking():
#     [{
#         'univentionShareSambaCustomSetting': [' ', '[foo]', 'path = /etc'],
#     }, {
#         'univentionShareSambaCustomSetting': ['\n[foo]\npath = /etc'],
#     }]
#
#
# def test_code_execution_path():
#     {
#         'univentionSharePath': ["/'; touch /tmp/hacked; true '"],
#     }
