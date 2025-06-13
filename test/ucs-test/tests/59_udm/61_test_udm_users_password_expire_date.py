#!/usr/share/ucs-test/runner python3
## desc: Check UDM users/user --set userexpiry
## roles: [domaincontroller_master]
## exposure: dangerous
## packages: [python3-univention-directory-manager]
## bugs: [25279,36330]

import calendar
import copy
import re
import time

import univention.admin.password
import univention.testing.strings as uts
import univention.testing.udm as udm_test
from univention.testing import utils
from univention.uldap import getMachineConnection


def ldap_obj_search(dn=None, ldapfilter='(objectClass=*)'):
    lo = getMachineConnection()
    if dn:
        result = lo.search(base=dn, scope='base', filter=ldapfilter)
    else:
        result = lo.search(filter=ldapfilter)

    assert result, f"No Objects found with filter: {ldapfilter}"
    assert len(result) == 1, "Too many objects (%d) found for filter '%s'" % (len(result), ldapfilter)

    (dn, obj) = result[0]
    return obj


def dictdiff(first, second):
    diff = {}
    for key in set(first) | set(second):
        try:
            x = first[key]
        except KeyError:
            diff[key] = (None, second[key])
            continue

        try:
            y = second[key]
        except KeyError:
            diff[key] = (x, None)
            continue

        if x != y:
            diff[key] = (x, y)
    return diff


def check_dict_values(obj, expectation):
    for attribute, value in expectation.items():
        if value is None:
            assert attribute not in obj, f"Attribute '{attribute}' found with value '{obj[attribute]}', expected to be unset"
        else:
            assert attribute in obj, f"Attribute '{attribute}' not found. Expected value: '{value}'"
            if value == []:  # special meaning: [] == "set to unspecified value"
                return
            assert obj[attribute] == value, f"Attribute '{attribute}' found with value '{obj[attribute]}'. Expected value: '{value}'"


def modify_and_diff(udm, **kwargs):
    before = ldap_obj_search(kwargs['dn'])
    udm.modify_object('users/user', **kwargs)
    utils.wait_for_connector_replication()
    after = ldap_obj_search(kwargs['dn'])
    return dictdiff(before, after)


def modify_and_check_expectation(udm, expected_diff=None, **kwargs):
    if expected_diff:
        diff = modify_and_diff(udm, **kwargs)
        ddiff = dictdiff(diff, expected_diff)
        assert not ddiff, "Unexpected diff: %s" % ddiff
    else:
        try:
            diff = modify_and_diff(udm, **kwargs)
        except udm_test.UCSTestUDM_NoModification:
            pass
        else:
            ddiff = dictdiff(diff, {})
            assert not ddiff, "Unexpected diff: %s" % ddiff


def syntax_date2_dateformat(userexpirydate):
    # Note: this is a timezone dependent value
    _re_iso = re.compile('^[0-9]{4}-[0-9]{2}-[0-9]{2}$')
    _re_de = re.compile(r'^[0-9]{1,2}\.[0-9]{1,2}\.[0-9]+$')
    if _re_iso.match(userexpirydate):
        return "%Y-%m-%d"
    elif _re_de.match(userexpirydate):
        return "%d.%m.%y"
    else:
        raise ValueError


def udm_formula_for_sambaKickoffTime(userexpirydate):
    # Note: this is a timezone dependent value
    dateformat = syntax_date2_dateformat(userexpirydate)
    return str(int(time.mktime(time.strptime(userexpirydate, dateformat)))).encode('ASCII')


def udm_formula_for_shadowExpire(userexpirydate):
    # Note: this is a timezone dependent value
    dateformat = syntax_date2_dateformat(userexpirydate)
    return str(int(calendar.timegm(time.strptime(userexpirydate, dateformat)) / 3600 / 24)).encode('ASCII')


SAMBAACCTFLAGS_NORMAL = b'[U          ]'
SAMBAACCTFLAGS_DISABLED = b'[UD         ]'
KRB5KDCFLAGS_NORMAL = str(int('01111110', 2)).encode('ASCII')
KRB5KDCFLAGS_REQUIRE_AS_REQ = str(int(KRB5KDCFLAGS_NORMAL) | (1 << 7)).encode('ASCII')


def run():
    with udm_test.UCSTestUDM() as udm:
        passwd = uts.random_string()
        uts.random_name()

        # Prepare user and check
        userdn, _username = udm.create_user(password=passwd, disabled="0")

        # since we don't expect a later diff, we have to wait for the domain SID
        # TODO: this should be done in a more generic way:1
        time.sleep(16)

        expected_after = ldap_obj_search(userdn)
        check_dict_values(expected_after, {
            'sambaAcctFlags': [SAMBAACCTFLAGS_NORMAL],
            'sambaKickoffTime': None,
            'krb5KDCFlags': [KRB5KDCFLAGS_NORMAL],
            'krb5ValidEnd': None,
            'shadowExpire': None,
        })

        # Modify and check
        new_uexp = "02.02.15"
        expected_before = copy.deepcopy(expected_after)
        expected_after.update({
            'sambaAcctFlags': [SAMBAACCTFLAGS_NORMAL],
            'sambaKickoffTime': [udm_formula_for_sambaKickoffTime(new_uexp)],
            'krb5KDCFlags': [KRB5KDCFLAGS_NORMAL],
            'krb5ValidEnd': [b'20150202000000Z'],
            'shadowExpire': [udm_formula_for_shadowExpire(new_uexp)],
        })
        expected_diff = dictdiff(expected_before, expected_after)
        modify_and_check_expectation(udm, expected_diff, dn=userdn, userexpiry=new_uexp)

        # Modify and check
        expected_before = copy.deepcopy(expected_after)
        expected_after.update({
            'sambaAcctFlags': [SAMBAACCTFLAGS_DISABLED],
            'sambaKickoffTime': [udm_formula_for_sambaKickoffTime(new_uexp)],
            'krb5KDCFlags': [KRB5KDCFLAGS_REQUIRE_AS_REQ],
            'krb5ValidEnd': [b'20150202000000Z'],
            'shadowExpire': [b'1'],
            'userPassword': [univention.admin.password.lock_password(expected_before['userPassword'][0].decode('ASCII')).encode('ASCII')],
        })
        expected_diff = dictdiff(expected_before, expected_after)
        modify_and_check_expectation(udm, expected_diff, dn=userdn, userexpiry="", disabled="1")

        # Modify and check
        expected_before = copy.deepcopy(expected_after)
        expected_after.update({
            'sambaAcctFlags': [SAMBAACCTFLAGS_NORMAL],
            'sambaKickoffTime': [udm_formula_for_sambaKickoffTime(new_uexp)],
            'krb5KDCFlags': [KRB5KDCFLAGS_NORMAL],
            'krb5ValidEnd': [b'20150202000000Z'],
            'shadowExpire': [udm_formula_for_shadowExpire(new_uexp)],
            'userPassword': [univention.admin.password.unlock_password(expected_before['userPassword'][0].decode('ASCII')).encode('ASCII')],
        })
        expected_diff = dictdiff(expected_before, expected_after)
        modify_and_check_expectation(udm, expected_diff, dn=userdn, userexpiry=new_uexp, disabled="0")

        # Modify and check
        new_uexp = "2014-01-01"
        expected_before = copy.deepcopy(expected_after)
        expected_after.update({
            'sambaAcctFlags': [SAMBAACCTFLAGS_NORMAL],
            'sambaKickoffTime': [udm_formula_for_sambaKickoffTime(new_uexp)],
            'krb5ValidEnd': [b'20140101000000Z'],
            'krb5KDCFlags': [KRB5KDCFLAGS_NORMAL],
            'shadowExpire': [udm_formula_for_shadowExpire(new_uexp)],
        })
        expected_diff = dictdiff(expected_before, expected_after)
        modify_and_check_expectation(udm, expected_diff, dn=userdn, userexpiry=new_uexp)

        # Modify and check
        expected_before = copy.deepcopy(expected_after)
        expected_after.update({
            'sambaAcctFlags': [SAMBAACCTFLAGS_DISABLED],
            'sambaKickoffTime': [udm_formula_for_sambaKickoffTime(new_uexp)],
            'krb5ValidEnd': [b'20140101000000Z'],
            'krb5KDCFlags': [KRB5KDCFLAGS_REQUIRE_AS_REQ],
            'shadowExpire': [b'1'],
            'userPassword': [univention.admin.password.lock_password(expected_before['userPassword'][0].decode('ASCII')).encode('ASCII')],
        })
        expected_diff = dictdiff(expected_before, expected_after)
        modify_and_check_expectation(udm, expected_diff, dn=userdn, disabled="1")

        # Modify and check
        new_uexp = "2015-02-02"
        expected_before = copy.deepcopy(expected_after)
        expected_after.update({
            'sambaAcctFlags': [SAMBAACCTFLAGS_DISABLED],
            'sambaKickoffTime': [udm_formula_for_sambaKickoffTime(new_uexp)],
            'krb5ValidEnd': [b'20150202000000Z'],
            'krb5KDCFlags': [KRB5KDCFLAGS_REQUIRE_AS_REQ],
            'shadowExpire': [udm_formula_for_shadowExpire(new_uexp)],
        })
        expected_diff = dictdiff(expected_before, expected_after)
        modify_and_check_expectation(udm, expected_diff, dn=userdn, userexpiry=new_uexp)

        # Modify and check
        new_uexp = "01.01.14"
        expected_before = copy.deepcopy(expected_after)
        expected_after.update({
            'sambaAcctFlags': [SAMBAACCTFLAGS_DISABLED],
            'sambaKickoffTime': [udm_formula_for_sambaKickoffTime(new_uexp)],
            'krb5KDCFlags': [KRB5KDCFLAGS_REQUIRE_AS_REQ],
            'krb5ValidEnd': [b'20140101000000Z'],
            'shadowExpire': [udm_formula_for_shadowExpire(new_uexp)],
        })
        expected_diff = dictdiff(expected_before, expected_after)
        modify_and_check_expectation(udm, expected_diff, dn=userdn, userexpiry=new_uexp, disabled="1")

        # Modify and check
        new_uexp = "02.02.15"
        expected_before = copy.deepcopy(expected_after)
        expected_after.update({
            'sambaAcctFlags': [SAMBAACCTFLAGS_NORMAL],
            'sambaKickoffTime': [udm_formula_for_sambaKickoffTime(new_uexp)],
            'krb5KDCFlags': [KRB5KDCFLAGS_NORMAL],
            'krb5ValidEnd': [b'20150202000000Z'],
            'shadowExpire': [udm_formula_for_shadowExpire(new_uexp)],
            'userPassword': [univention.admin.password.unlock_password(expected_before['userPassword'][0].decode('ASCII')).encode('ASCII')],
        })
        expected_diff = dictdiff(expected_before, expected_after)
        modify_and_check_expectation(udm, expected_diff, dn=userdn, userexpiry=new_uexp, disabled="0")

        # Modify and check
        expected_diff = {}
        modify_and_check_expectation(udm, expected_diff, dn=userdn, disabled="0")

        # Modify and check
        modify_and_check_expectation(udm, expected_diff, dn=userdn, userexpiry="")


if __name__ == '__main__':
    run()
