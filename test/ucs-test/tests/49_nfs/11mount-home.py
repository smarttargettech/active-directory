#!/usr/share/ucs-test/runner python3
## desc: Login user with $HOME on NFS share
## roles: [domaincontroller_backup, domaincontroller_slave, memberserver]
## exposure: dangerous
## tags: [skip_admember]
## packages:
##   - univention-home-mounter

from os.path import ismount, join
from subprocess import PIPE, Popen
from time import sleep

from univention.testing.strings import random_name, random_username
from univention.testing.ucr import UCSTestConfigRegistry
from univention.testing.udm import UCSTestUDM
from univention.testing.utils import fail, wait_for_replication


if __name__ == '__main__':
    ucr = UCSTestConfigRegistry()
    ucr.load()

    with UCSTestUDM() as udm:
        share_name = random_name()
        share_path = join('/mnt', share_name)
        share_prop = {
            "name": share_name,
            "host": '%(ldap/master)s' % ucr,
            "path": share_path,
            "nfs_hosts": ['%(hostname)s' % ucr],  # FQHN not supported
            "root_squash": '0',
            "options": ['nfs'],
        }
        share = udm.create_object('shares/share', **share_prop)

        user_name = random_username()
        user_home = join('/home', user_name)
        user_prop = {
            "username": user_name,
            "unixhome": user_home,
            "primaryGroup": 'cn=%s,cn=groups,%s' % (ucr.get('groups/default/domainadmins', 'Domain Admins'), ucr['ldap/base']),
            "homeShare": share,
            "homeSharePath": user_name,
        }
        user, _user_name = udm.create_user(**user_prop)

        print('Waiting 30s for UDL.postrun() on master to export share...')
        sleep(30)
        wait_for_replication()

        print('1st login...')
        p1 = Popen(('su', '-c', 'cat', '-l', user_name), stdin=PIPE)
        for _ in range(60):
            if ismount(user_home):
                break
            sleep(1)
        else:
            fail('Failed to mount %r' % user_home)

        print('2nd login...')
        p2 = Popen(('su', '-c', 'df .', '-l', user_name), stdout=PIPE)

        p1.communicate(b'1st')
        stdout, _stderr = p2.communicate()
        stdout = stdout.decode('UTF-8')
        ret = (p1.wait(), p2.wait())
        print(stdout, ret)

        Popen(('umount', '-l', '-f', user_home)).wait()

        if any(ret) or share_path not in stdout:
            fail('Failed: %r %r' % (stdout, ret))
