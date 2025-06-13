#!/usr/share/ucs-test/runner python3
## desc: Test mailForwardAddress and mailForwardCopyToSelf
## tags: [udm,apptest]
## exposure: dangerous
## packages:
##   - univention-config
##   - univention-directory-manager-tools
##   - univention-mail-server

# pylint: disable=attribute-defined-outside-init

import random
import tempfile
import time

import dns.resolver

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils
from univention.testing.mail import MailSink, MailSinkGuard
from univention.testing.network import NetworkRedirector

from essential.mail import check_delivery, send_mail, set_mail_forward_copy_to_self_ucrv


TIMEOUT = 600  # in seconds


class Bunch:
    """
    >>> y = Bunch(foo=42, bar='TEST')
    >>> print(repr(y.foo), repr(y.bar))
    42 'TEST'

    >>> x = Bunch()
    >>> x.a = 4
    >>> print(x.a)
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


def check_delivery_mailsink(token, mailsink_files, should_be_delivered):
    delivered = False
    print("Waiting for an email delivery")
    for _i in range(TIMEOUT):
        for fn in mailsink_files:
            if token in open(fn).read():
                delivered = True
                print('Mail delivered to sink %r' % (fn,))
                break
        if not delivered:
            time.sleep(1)
        else:
            break
    if should_be_delivered != delivered:
        utils.fail('Mail sent with token = %r, delivered to the mail sink = %r   expected=%r' % (token, delivered, should_be_delivered))


def send_and_check(user, sink_files, in_mail_sink, in_local):
    # send mails
    for addr, msg in (
            (user.mailPrimaryAddress, 'sending mail to mailPrimaryAddress'),
            (user.mailAlternativeAddress, 'sending mail to mailAlternativeAddress'),
    ):
        print('*** %s' % (msg,))
        token = f'token: {str(time.time())!r}'
        send_mail(
            recipients=addr,
            msg=token,
        )
        # check if mail has been delivered to mailsink AND locally
        check_delivery_mailsink(token, [x.name for x in sink_files], in_mail_sink)
        check_delivery(token, user.mailPrimaryAddress, in_local)


def test_mail_forward(mail_copy_to_self):
    set_mail_forward_copy_to_self_ucrv(mail_copy_to_self)
    mail_copy_to_self = mail_copy_to_self == 'yes'
    with ucr_test.UCSTestConfigRegistry() as ucr, udm_test.UCSTestUDM() as udm, MailSinkGuard() as mail_sink_guard, NetworkRedirector() as nethelper:
        domain = ucr.get('domainname').lower()

        # get IP addresses of the MX of "univention.de"
        # FIXME: perform a dynamic lookup
        mx_addresses = [
            dns.resolver.query('mx00.kundenserver.de', 'A')[0].address,
            dns.resolver.query('mx01.kundenserver.de', 'A')[0].address,
        ]
        # setup mailsink and network redirector
        port = random.randint(60000, 61000)
        sink_files = []
        mail_sinks = []
        for mx_addr in mx_addresses:
            tmpfd = tempfile.NamedTemporaryFile(suffix='.eml', dir='/tmp')
            nethelper.add_redirection(mx_addr, 25, port)
            sink = MailSink('127.0.0.1', port, filename=tmpfd.name)
            mail_sink_guard.add(sink)
            sink.start()
            port += 1
            mail_sinks.append(sink)
            sink_files.append(tmpfd)

        # create user with mPA, mFA and Copy2Self=1
        user = Bunch()
        user.mailPrimaryAddress = '%s@%s' % (uts.random_string(), domain)
        user.mailAlternativeAddress = ['%s@%s' % (uts.random_string(), domain)]
        user.mailHomeServer = '%s.%s' % (ucr.get('hostname'), domain)
        user.mailForwardAddress = ['noreply@univention.de']
        user.dn, user.username = udm.create_user(set={
            'mailHomeServer': user.mailHomeServer,
            'mailPrimaryAddress': user.mailPrimaryAddress,
            'mailAlternativeAddress': user.mailAlternativeAddress,
            'mailForwardAddress': user.mailForwardAddress,
            'mailForwardCopyToSelf': '1',
        })

        if mail_copy_to_self:
            utils.verify_ldap_object(
                user.dn,
                {
                    'univentionMailHomeServer': [user.mailHomeServer],
                    'mailPrimaryAddress': [user.mailPrimaryAddress],
                    'mailAlternativeAddress': user.mailAlternativeAddress,
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
                    'mailAlternativeAddress': user.mailAlternativeAddress,
                    'mailForwardAddress': [*user.mailForwardAddress, user.mailPrimaryAddress],
                },
                strict=True)

        send_and_check(user, sink_files, in_mail_sink=True, in_local=True)
        # disable copy to self
        udm.modify_object(
            'users/user',
            dn=user.dn,
            set={
                'mailForwardCopyToSelf': '0',
            })
        send_and_check(user, sink_files, in_mail_sink=True, in_local=False)


if __name__ == '__main__':
    test_mail_forward('no')
    test_mail_forward('yes')
