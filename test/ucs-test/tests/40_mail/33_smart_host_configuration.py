#!/usr/share/ucs-test/runner python3
## desc: Test smart host configuration
## roles-not: [memberserver]
## tags: [skip_admember]
## exposure: dangerous

import tempfile
import time

import dns.resolver

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.config_registry import handler_set
from univention.testing import utils
from univention.testing.mail import MailSink
from univention.testing.network import NetworkRedirector

from essential.mail import check_delivery, restart_postfix, send_mail


TIMEOUT = 90  # sec


def check_delivery_mailsink(token, mailsink_file, should_be_delivered):
    delivered = False
    print("Waiting for an email delivery to a mailsink")
    for _i in range(TIMEOUT):
        if token in open(mailsink_file).read():
            delivered = True
            print('Mail Delivered')
            break
        else:
            time.sleep(1)
    if should_be_delivered != delivered:
        utils.fail('Mail sent with token = %r, Delivered to the mail sink = %r' % (token, delivered))


def wait_for_dns(hosts):
    for host, ip in hosts:
        found = None
        for _i in range(TIMEOUT):
            try:
                found = dns.resolver.query(host, 'A')[0].address
                break
            except dns.resolver.NXDOMAIN:
                time.sleep(1)
        if found != ip:
            utils.fail('DNS query answer address found = %s, expected = %s' % (found, ip))


def main():
    with ucr_test.UCSTestConfigRegistry() as ucr:
        with udm_test.UCSTestUDM() as udm:
            with NetworkRedirector() as nethelper:
                dcslave = uts.random_name()
                domain = ucr.get('domainname')
                basedn = ucr.get('ldap/base')
                dcslave_ip = uts.random_ip()
                udm.create_object(
                    'computers/domaincontroller_slave',
                    set={
                        'ip': dcslave_ip,
                        'name': dcslave,
                        'dnsEntryZoneForward': 'zoneName=%s,cn=dns,%s %s' % (
                            domain, basedn, dcslave_ip),
                    },
                    position='cn=computers,%s' % basedn,
                )
                dcslave_fqdn = '%s.%s' % (dcslave, domain)
                handler_set(['mail/relayhost=%s' % dcslave_fqdn])
                port = 60025
                nethelper.add_redirection(dcslave_ip, 25, port)
                wait_for_dns([(dcslave, dcslave_ip)])
                restart_postfix()
                with tempfile.NamedTemporaryFile(suffix='.eml', dir='/tmp') as fp, MailSink('127.0.0.1', port, filename=fp.name):
                    recipient = 'noreply@univention.de'
                    token = str(time.time())
                    send_mail(recipients=recipient, msg=token)
                    check_delivery_mailsink(token, fp.name, True)
                    check_delivery(token, recipient, False)


if __name__ == '__main__':
    main()
