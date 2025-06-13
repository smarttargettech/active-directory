#!/usr/share/ucs-test/runner python3
## desc: Check if there are any school-slaves with the attribute userAccountControl of a windows computer
## packages: [ucs-school-import, univention-samba4, univention-s4-connector]
## bugs: [50280]
## roles:
## - domaincontroller_master
## tags: [apptest]
## exposure: safe

from subprocess import PIPE, Popen

from ldap.filter import filter_format

from univention.testing import utils


if __name__ == '__main__':
    print("\nChecking if the attribute userAccountControl is set correctly on all domaincontroller slaves")

    schoolslaves_cn = [x[1]['cn'][0] for x in utils.get_ldap_connection().search('univentionObjectType=computers/domaincontroller_slave', attr=['cn'])]
    print(f'List of Ucs-school-slaves: {schoolslaves_cn}')

    for slave in schoolslaves_cn:
        p2 = Popen(['univention-s4search', '--cross-ncs', filter_format('(&(cn=%s)(userAccountControl:1.2.840.113556.1.4.803:=4096))', (slave,))], stdout=PIPE, stderr=PIPE, shell=False)
        (stdout, stderr) = p2.communicate()
        faulty_schools = []
        for line in stdout.strip().splitlines():
            if line.startswith('dn:'):
                faulty_schools.append(line.split(':')[1])
        if faulty_schools:
            utils.fail(f"\nTest failed. School slaves with incorrect userAccountControl found.\n{faulty_schools}\n")
