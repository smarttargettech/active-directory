#!/usr/share/ucs-test/runner python3
## desc: Create and remove shared folders with different settings of mail/dovecot/mailbox/delete
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

from essential.mail import create_shared_mailfolder, get_dovecot_shared_folder_maildir, random_email


TIMEOUT_MAIL = 10
timeout = 1


class Bunch:

    def __init__(self, **kwds):
        self.__dict__.update(kwds)

    def __repr__(self):
        return repr(self.__dict__)


def main():
    with utils.AutomaticListenerRestart():
        with udm_test.UCSTestUDM() as udm:
            with ucr_test.UCSTestConfigRegistry() as ucr:
                handler_set([
                    'mail/dovecot/logging/auth_debug=yes', 'mail/dovecot/logging/auth_debug_passwords=yes',
                    'mail/dovecot/logging/auth_verbose=yes', 'mail/dovecot/logging/auth_verbose_passwords=yes',
                    'mail/dovecot/logging/mail_debug=yes'])
                fqdn = '%(hostname)s.%(domainname)s' % ucr
                user_addr = random_email()
                logfiles = ['/var/log/dovecot.log', '/var/log/univention/listener.log']
                with utils.FollowLogfile(logfiles=logfiles):
                    with utils.AutoCallCommand(enter_cmd=['doveadm', 'log', 'reopen'], exit_cmd=['doveadm', 'log', 'reopen']):
                        _user_dn, _user_name = udm.create_user(
                            set={
                                'mailHomeServer': fqdn,
                                'mailPrimaryAddress': user_addr,
                            })

                        #
                        # test creating shared folder with different delete flags
                        #
                        for i, with_mailaddress, flag_delete in [
                                (0, False, 'no'),
                                (1, False, 'yes'),
                                (2, True, 'no'),
                                (3, True, 'yes')]:

                            #
                            # reconfigure system
                            #
                            handler_set([
                                'mail/dovecot/mailbox/rename=yes',
                                'mail/dovecot/mailbox/delete=%s' % (flag_delete,),
                            ])
                            utils.restart_listener()
                            utils.wait_for_replication()

                            # create folder
                            dn, name, address = create_shared_mailfolder(udm, fqdn, mailAddress=with_mailaddress, user_permission=['"%s" "%s"' % (user_addr, 'all')])
                            folder = Bunch(dn=dn, name=name, mail_address=address)

                            print(folder)

                            # check folder with mail address
                            path = get_dovecot_shared_folder_maildir(folder.name)
                            if not os.path.exists(path):
                                utils.fail('Test %d: maildir %r for shared folder does not exist! %r' % (i, path, folder))

                            udm.remove_object('mail/folder', dn=folder.dn)

                            # check folder removal
                            if os.path.exists(path) and flag_delete == 'yes':
                                utils.fail('Test %d: maildir %r for shared folder has not been removed! %r' % (i, path, folder))
                            elif not os.path.exists(path) and flag_delete == 'no':
                                utils.fail('Test %d: maildir %r for shared folder has been removed! %r' % (i, path, folder))


if __name__ == '__main__':
    main()
