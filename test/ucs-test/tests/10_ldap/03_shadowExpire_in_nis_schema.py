#!/usr/share/ucs-test/runner python3
## desc: Allow comparison of shadowExpire in nis.schema
## roles: [domaincontroller_master, domaincontroller_backup, domaincontroller_slave]
## exposure: dangerous
## packages: [univention-ldap-server]
## bugs: [35329, 35088]
## versions:
##  4.0-2: skip

import re
from datetime import datetime, timedelta

import univention.testing.strings as uts
import univention.testing.udm as udm_test
from univention.testing import utils
from univention.uldap import getMachineConnection


def nis_schema_conatains_ordering_for_shadowExpire():
    NIS_FILE = '/etc/ldap/schema/nis.schema'
    pattern = re.compile(r'(attributetype\s\(\s\d{1,4}\.\d{1,4}\.\d{1,4}\.\d{1,4}\.\d{1,4}\.\d{1,4}\.\d{1,4}\.\d{1,4}\sNAME\s\'shadowExpire\'[^\(]+ORDERING\sintegerOrderingMatch[^\)]+\))')
    with open(NIS_FILE) as fi:
        search_obj = re.search(pattern, fi.read())
        return search_obj.groups()


def ldap_search(filter_):
    lo = getMachineConnection()
    found = lo.search(filter=filter_)
    if found:
        return [(x[1]['uid'][0].decode('UTF-8'), x[1]['shadowExpire'][0].decode('ASCII')) for x in found]


def run():
    with udm_test.UCSTestUDM() as udm:
        def create_users(date_diff):
            current_time = datetime.utcnow()
            chosen_time = current_time + timedelta(days=date_diff)

            expiry_date = chosen_time.strftime("%Y-%m-%d")
            passwd = uts.random_string()
            username = uts.random_name()
            _userdn, username = udm.create_user(password=passwd, userexpiry=expiry_date)
            expiry_ldap = int(ldap_search('uid=%s' % username)[0][1])  # get the real set value from ldap
            return username, passwd, expiry_ldap

        test_list = []
        for date_diff in [-2, 0, 2]:  # Numbers represent days, - in the past, + in the future, 0 = today
            test_list.append(create_users(date_diff))

        for username, _passwd, date in test_list:
            print(f'\nSearching LDAP filter=(&(objectClass=posixAccount)(shadowExpire>={date - 1!r})(shadowExpire<={date + 1!r}))')
            ldap_found = ldap_search(f'(&(objectClass=posixAccount)(shadowExpire>={date - 1!r})(shadowExpire<={date + 1!r}))')
            exclude_list = [(x[0], x[2]) for x in test_list]
            exclude_list.remove((username, date))
            if ldap_found:
                print(f"Should be found: [(username, expirydate)] = [('{username}', '{date}')]")
                print('Found in LDAP:   [(username, expirydate)] = %r' % ldap_found)
                if ((username, str(date)) not in ldap_found or set(exclude_list).issubset(ldap_found)):
                    utils.fail(f"LDAP is not able to sort Objects with filter: (shadowExpire>={date - 1!r})(shadowExpire<={date + 1!r})")


def main():
    nis = nis_schema_conatains_ordering_for_shadowExpire()
    print('nis.schema contains:\n%s' % nis)
    if not nis:
        utils.fail("nis.schema does not contain ordering for shadowExpire")
    run()


if __name__ == '__main__':
    main()
