#!/usr/share/ucs-test/runner python3
## desc: Test UDM properties mailForwardAddress and mailForwardCopyToSelf
## tags: [udm,apptest]
## exposure: unsafe
## packages:
##   - univention-config
##   - univention-directory-manager-tools
##   - univention-mail-server

# pylint: disable=attribute-defined-outside-init

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils

from essential.mail import set_mail_forward_copy_to_self_ucrv


class Bunch:
    """
    >>> y = Bunch(foo=42, bar='TEST')
    >>> print repr(y.foo), repr(y.bar)
    42 'TEST'

    >>> x = Bunch()
    >>> x.a = 4
    >>> print x.a
    4
    """

    def __init__(self, **kwds):
        self.__dict__.update(kwds)

    def __str__(self):
        result = []
        for key, value in self.__dict__.items():
            result.append('%s=%r' % (key, value))
        return 'Bunch(' + ', '.join(result) + ')'

    def __repr__(self):
        return str(self)


def test_mail_forward(mail_copy_to_self):
    set_mail_forward_copy_to_self_ucrv(mail_copy_to_self)
    mail_copy_to_self = mail_copy_to_self == 'yes'
    with ucr_test.UCSTestConfigRegistry() as ucr:
        with udm_test.UCSTestUDM() as udm:
            domain = ucr.get('domainname').lower()

            # create user with mPA
            user = Bunch()
            user.mailPrimaryAddress = '%s@%s' % (uts.random_string(), domain)
            user.mailHomeServer = '%s.%s' % (ucr.get('hostname'), domain)
            user.mailForwardAddress = []
            user.dn, user.username = udm.create_user(set={
                'mailHomeServer': user.mailHomeServer,
                'mailPrimaryAddress': user.mailPrimaryAddress,
            })
            utils.verify_ldap_object(
                user.dn,
                {
                    'univentionMailHomeServer': [user.mailHomeServer],
                    'mailPrimaryAddress': [user.mailPrimaryAddress],
                    'mailForwardAddress': user.mailForwardAddress,
                },
                strict=True)

            # set mFA without Copy2Self
            user.mailForwardAddress = [
                'fwd1-%s@univention.de' % (user.username,),
                'fwd2-%s@univention.de' % (user.username,),
            ]
            udm.modify_object('users/user', dn=user.dn, mailForwardAddress=user.mailForwardAddress)
            utils.verify_ldap_object(
                user.dn,
                {
                    'univentionMailHomeServer': [user.mailHomeServer],
                    'mailPrimaryAddress': [user.mailPrimaryAddress],
                    'mailForwardAddress': user.mailForwardAddress,
                },
                strict=True)

            # change mFA without Copy2Self
            user.mailForwardAddress = [
                'fwd2-%s@univention.de' % (user.username,),
                'fwd3-%s@univention.de' % (user.username,),
            ]
            udm.modify_object('users/user', dn=user.dn, set={'mailForwardAddress': user.mailForwardAddress})
            utils.verify_ldap_object(
                user.dn,
                {
                    'univentionMailHomeServer': [user.mailHomeServer],
                    'mailPrimaryAddress': [user.mailPrimaryAddress],
                    'mailForwardAddress': user.mailForwardAddress,
                },
                strict=True)

            # set Copy2Self=1
            udm.modify_object('users/user', dn=user.dn, mailForwardCopyToSelf='1')
            if mail_copy_to_self:
                utils.verify_ldap_object(
                    user.dn,
                    {
                        'univentionMailHomeServer': [user.mailHomeServer],
                        'mailPrimaryAddress': [user.mailPrimaryAddress],
                        'mailForwardAddress': user.mailForwardAddress,
                        'mailForwardCopyToSelf': '1',
                    },
                    strict=True)
            else:
                utils.verify_ldap_object(
                    user.dn,
                    {
                        'univentionMailHomeServer': [user.mailHomeServer],
                        'mailPrimaryAddress': [user.mailPrimaryAddress],
                        'mailForwardAddress': [*user.mailForwardAddress, user.mailPrimaryAddress],
                    },
                    strict=True)

            # change mFA and set Copy2Self=0
            user.mailForwardAddress = [
                'fwd4-%s@univention.de' % (user.username,),
            ]
            udm.modify_object(
                'users/user',
                dn=user.dn,
                set={
                    'mailForwardAddress': user.mailForwardAddress,
                    'mailForwardCopyToSelf': '0',
                })
            if mail_copy_to_self:
                utils.verify_ldap_object(user.dn, {
                    'univentionMailHomeServer': [user.mailHomeServer],
                    'mailPrimaryAddress': [user.mailPrimaryAddress],
                    'mailForwardAddress': user.mailForwardAddress,
                    'mailForwardCopyToSelf': '0',
                }, strict=True)
            else:
                utils.verify_ldap_object(user.dn, {
                    'univentionMailHomeServer': [user.mailHomeServer],
                    'mailPrimaryAddress': [user.mailPrimaryAddress],
                    'mailForwardAddress': user.mailForwardAddress,
                }, strict=True)

            # change mFA and set Copy2Self=1
            user.mailForwardAddress = [
                'fwd5-%s@univention.de' % (user.username,),
                'fwd6-%s@univention.de' % (user.username,),
                'fwd7-%s@univention.de' % (user.username,),
            ]
            udm.modify_object(
                'users/user',
                dn=user.dn,
                set={
                    'mailForwardAddress': user.mailForwardAddress,
                    'mailForwardCopyToSelf': '1',
                })
            if mail_copy_to_self:
                utils.verify_ldap_object(
                    user.dn,
                    {
                        'univentionMailHomeServer': [user.mailHomeServer],
                        'mailPrimaryAddress': [user.mailPrimaryAddress],
                        'mailForwardAddress': user.mailForwardAddress,
                        'mailForwardCopyToSelf': '1',
                    },
                    strict=True)
            else:
                utils.verify_ldap_object(
                    user.dn,
                    {
                        'univentionMailHomeServer': [user.mailHomeServer],
                        'mailPrimaryAddress': [user.mailPrimaryAddress],
                        'mailForwardAddress': [*user.mailForwardAddress, user.mailPrimaryAddress],
                    },
                    strict=True)

            # remove mFA and keep Copy2Self=1
            udm.modify_object(
                'users/user',
                dn=user.dn,
                mailForwardCopyToSelf='1',
                remove={'mailForwardAddress': user.mailForwardAddress})
            if mail_copy_to_self:
                utils.verify_ldap_object(
                    user.dn,
                    {
                        'univentionMailHomeServer': [user.mailHomeServer],
                        'mailPrimaryAddress': [user.mailPrimaryAddress],
                        'mailForwardAddress': [],
                        'mailForwardCopyToSelf': '1',
                    },
                    strict=True)
            else:
                utils.verify_ldap_object(
                    user.dn,
                    {
                        'univentionMailHomeServer': [user.mailHomeServer],
                        'mailPrimaryAddress': [user.mailPrimaryAddress],
                        'mailForwardAddress': [],
                    },
                    strict=True)

            # create second user with mPA, mFA and Copy2Self
            user = Bunch()
            user.mailPrimaryAddress = '%s@%s' % (uts.random_string(), domain)
            user.mailHomeServer = '%s.%s' % (ucr.get('hostname'), domain)
            user.mailForwardAddress = [
                'fwd5-%s@univention.de' % (uts.random_string(),),
                'fwd6-%s@univention.de' % (uts.random_string(),),
            ]
            user.dn, user.username = udm.create_user(set={
                'mailHomeServer': user.mailHomeServer,
                'mailPrimaryAddress': user.mailPrimaryAddress,
                'mailForwardAddress': user.mailForwardAddress,
                'mailForwardCopyToSelf': '1',
            })
            if mail_copy_to_self:
                utils.verify_ldap_object(
                    user.dn,
                    {
                        'univentionMailHomeServer': [user.mailHomeServer],
                        'mailPrimaryAddress': [user.mailPrimaryAddress],
                        'mailForwardAddress': user.mailForwardAddress,
                        'mailForwardCopyToSelf': '1',
                    },
                    strict=True)
            else:
                utils.verify_ldap_object(
                    user.dn,
                    {
                        'univentionMailHomeServer': [user.mailHomeServer],
                        'mailPrimaryAddress': [user.mailPrimaryAddress],
                        'mailForwardAddress': [*user.mailForwardAddress, user.mailPrimaryAddress],
                    },
                    strict=True)

            # create third user without mPA but mFA
            user = Bunch()
            user.mailHomeServer = '%s.%s' % (ucr.get('hostname'), domain)
            user.mailForwardAddress = ['noreply@univention.de']
            try:
                user.dn, user.username = udm.create_user(set={
                    'mailHomeServer': user.mailHomeServer,
                    'mailForwardAddress': user.mailForwardAddress,
                    'mailForwardCopyToSelf': '1',
                })
            except udm_test.UCSTestUDM_CreateUDMObjectFailed:
                print('OK: Creation of user without mPA but mFA failed as expected')
            else:
                utils.fail('Creation of user without mPA but mFA was unexpectedly successful')


if __name__ == '__main__':
    test_mail_forward('no')
    test_mail_forward('yes')
