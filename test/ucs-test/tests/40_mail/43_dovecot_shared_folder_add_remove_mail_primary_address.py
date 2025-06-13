#!/usr/share/ucs-test/runner python3
## desc: Add and remove mail primary address from shared folders
## tags: [apptest]
## exposure: dangerous
## packages:
##  - univention-mail-server
##  - univention-mail-dovecot
##  - univention-directory-manager-tools

import os

import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.config_registry import handler_set
from univention.testing import utils

from essential.mail import (
    create_shared_mailfolder, get_dovecot_maildir, get_dovecot_shared_folder_maildir, random_email,
)


TIMEOUT_MAIL = 10


class Bunch:

    def __init__(self, **kwds):
        self.__dict__.update(kwds)

    def __repr__(self):
        return repr(self.__dict__)


def main():
    with utils.AutomaticListenerRestart():
        with udm_test.UCSTestUDM() as udm:
            with ucr_test.UCSTestConfigRegistry() as ucr:
                fqdn = '%(hostname)s.%(domainname)s' % ucr
                user_addr = random_email()
                _user_dn, _user_name = udm.create_user(
                    set={
                        'mailHomeServer': fqdn,
                        'mailPrimaryAddress': user_addr,
                    })

                #
                # test creating shared folder with different delete flags
                #
                for i, flag_rename in enumerate((True, False)):
                    #
                    # reconfigure system
                    #
                    handler_set([
                        'mail/dovecot/mailbox/rename=%s' % (flag_rename,),
                        'mail/dovecot/mailbox/delete=yes',
                    ])
                    utils.restart_listener()
                    utils.wait_for_replication()

                    # create folder
                    dn, name, address = create_shared_mailfolder(udm, fqdn, user_permission=['"%s" "%s"' % (user_addr, 'all')])
                    folder = Bunch(dn=dn, name=name, mail_address=address)

                    # check folder with mail address
                    old_path = get_dovecot_shared_folder_maildir(folder.name)
                    if not os.path.exists(old_path):
                        utils.fail('Test %d: maildir %r for shared folder does not exist! %r' % (i, old_path, folder))

                    # add a primary mail address to shared folder
                    new_address = random_email()
                    new_path = get_dovecot_maildir(new_address)
                    udm.modify_object('mail/folder', dn=folder.dn, set={'mailPrimaryAddress': new_address})

                    # check folder removal
                    if os.path.exists(old_path):
                        utils.fail('Test %d (flag_rename=%s): old maildir %r for shared folder has not been renamed! %r' % (i, flag_rename, old_path, folder))
                    if not os.path.exists(new_path):
                        utils.fail('Test %d (flag_rename=%s): maildir %r for shared folder has not been created/renamed! %r' % (i, flag_rename, new_path, folder))

                    # remove primary mail address to shared folder
                    udm.modify_object('mail/folder', dn=folder.dn, set={'mailPrimaryAddress': ''})

                    # check folder removal
                    if not os.path.exists(old_path):
                        utils.fail('Test %d (flag_rename=%s): original maildir %r for shared folder has not been created/renamed! %r' % (i, flag_rename, old_path, folder))
                    if os.path.exists(new_path):
                        utils.fail('Test %d (flag_rename=%s): new maildir %r for shared folder has not been renamed! %r' % (i, flag_rename, new_path, folder))


if __name__ == '__main__':
    global timeout  # noqa: PLW0604
    timeout = 1
    main()
