#!/usr/share/ucs-test/runner python3
## desc: POP3 mail login
## tags: [apptest]
## exposure: dangerous
## packages: [univention-mail-server]
## bugs: []

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils

from essential.mail import PopMail


def main():
    with ucr_test.UCSTestConfigRegistry() as ucr:
        with udm_test.UCSTestUDM() as udm:
            usermail = '%s@%s' % (uts.random_name(), ucr.get('domainname'))
            password = uts.random_string()
            _userdn, username = udm.create_user(
                password=password,
                mailPrimaryAddress=usermail,
                mailHomeServer='{}.{}'.format(ucr.get('hostname'), ucr.get('domainname')),
            )

            pop = PopMail()

            print('* Test pop login with the correct password:')
            if not pop.login_OK(usermail, password):
                utils.fail('POP3 login with mailPrimaryAddress failed with the correct password')

            print('* Test pop login with the wrong password:')
            if pop.login_OK(usermail, uts.random_name()):
                utils.fail('POP3 login with mailPrimaryAddress succeeded with the wrong password')

            print('* Test pop login with the correct password but with username instead of mailPrimaryAddress:')
            if not pop.login_OK(username, password):
                utils.fail('POP3 login with username failed with the correct password')

            print('* Test pop login with username and wrong password:')
            if pop.login_OK(username, uts.random_name()):
                utils.fail('POP3 login with username succeeded with the wrong password')


if __name__ == '__main__':
    main()
