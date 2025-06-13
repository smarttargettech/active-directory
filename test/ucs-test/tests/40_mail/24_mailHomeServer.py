#!/usr/share/ucs-test/runner python3
## desc: Mail home server
## tags: [apptest]
## exposure: dangerous
## packages: [univention-mail-server]

import tempfile
import time

import dns.resolver

import univention.admin.uldap
import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.admin.uexceptions import authFail
from univention.testing import utils
from univention.testing.mail import MailSink
from univention.testing.network import NetworkRedirector

from essential.mail import check_delivery, send_mail


TIMEOUT = 60  # sec


def check_delivery_mailsink(token, mailsink_file, should_be_delivered):
    delivered = False
    print("Waiting for an email delivery")
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
        for _i in range(TIMEOUT):
            try:
                dns.resolver.query(host, 'A')
                break
            except dns.resolver.NXDOMAIN:
                time.sleep(1)
        found = dns.resolver.query(host, 'A')[0].address
        if found != ip:
            utils.fail('DNS query answer address found = %s, expected = %s' % (found, ip))


def main():
    with udm_test.UCSTestUDM() as udm:
        with NetworkRedirector() as nethelper:
            password = 'univention'
            with ucr_test.UCSTestConfigRegistry() as ucr:
                domain = ucr.get('domainname')
                basedn = ucr.get('ldap/base')
            hosts = []
            for i in range(2):
                ip = uts.random_ip()
                host = uts.random_name()
                hosts.append(('%s.%s' % (host, domain), ip))
                udm.create_object(
                    'computers/domaincontroller_slave',
                    set={
                        'ip': ip,
                        'name': host,
                        'dnsEntryZoneForward': 'zoneName=%s,cn=dns,%s %s' % (
                            domain, basedn, ip),
                    },
                    position='cn=computers,%s' % basedn,
                )
            mails_list = []
            for mailHomeServer, _ in hosts:
                mail = '%s@%s' % (uts.random_name(), domain)
                user_dn, _username = udm.create_user(
                    set={
                        'password': password,
                        'mailPrimaryAddress': mail,
                        'mailHomeServer': mailHomeServer,
                    },
                )
                try:
                    univention.admin.uldap.access(binddn=user_dn, bindpw=password, host=ucr['ldap/master'])
                    print('*** OK: user can bind to LDAP server.')
                except authFail:
                    utils.fail('User cannot bind to LDAP server.')
                mails_list.append(mail)

            port = 60025
            sink_files = []
            mail_sinks = []
            try:
                for mailHomeServer, ip in hosts:
                    f = tempfile.NamedTemporaryFile(suffix='.eml', dir='/tmp')
                    nethelper.add_redirection(ip, 25, port)
                    ms = MailSink('127.0.0.1', port, filename=f.name, fqdn=mailHomeServer)
                    ms.start()
                    port += 1
                    mail_sinks.append(ms)
                    sink_files.append(f)

                wait_for_dns(hosts)
                for i, mail in enumerate(mails_list):
                    token = str(time.time())
                    send_mail(
                        recipients=mail,
                        msg=token,
                        tls=True,
                        username=mail,
                        password=password,
                    )
                    check_delivery(token, mail, False)
                    print('*** OK: mail was not delivered to systemmail/Dovecot.')
                    check_delivery_mailsink(token, sink_files[0].name, (i == 0))
                    print('*** OK: mail was{} sent to mailsink 1.'.format(' not' if i != 0 else ''))
                    check_delivery_mailsink(token, sink_files[1].name, (i == 1))
                    print('*** OK: mail was{} sent to mailsink 2.'.format(' not' if i != 1 else ''))
            finally:
                for ms in mail_sinks:
                    ms.stop()
                for f in sink_files:
                    f.close()


if __name__ == '__main__':
    main()
