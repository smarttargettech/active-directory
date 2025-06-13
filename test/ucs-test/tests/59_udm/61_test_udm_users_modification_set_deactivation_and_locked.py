#!/usr/share/ucs-test/runner pytest-3 -s -l -vv
## desc: Test changing disabled and locked simultaneously
## tags: [udm]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - univention-directory-manager-tools

import random
import subprocess
import time

import univention.admin.uldap


disabled_states = ('1', '0')
locked_states = ['0', '1']

transitions_log = []


def test_user_modification_set_deactivation_and_locked(udm, ldap_base):
    """Test changing disabled and locked simultaneously"""
    user_dn = None
    locked_state2 = locked_states.pop(random.randint(0, len(locked_states) - 1))
    while locked_states:
        locked_state1 = locked_states.pop(random.randint(0, len(locked_states) - 1))
        disabled_states_list = list(disabled_states)
        disabled_state1 = disabled_states_list.pop(random.randint(0, len(disabled_states_list) - 1))
        user_dn = modify_and_check(udm, ldap_base, user_dn, disabled_state1, locked_state1)
        while disabled_states_list:
            disabled_state2 = disabled_states_list.pop(random.randint(0, len(disabled_states_list) - 1))
            modify_and_check(udm, ldap_base, user_dn, disabled_state2, locked_state2)
            modify_and_check(udm, ldap_base, user_dn, disabled_state1, locked_state1)

    transitions_log.pop(-1)
    print_transitions()


def print_transitions():
    print('    disabled         | locked   -> disabled         | locked')
    print('------------------------------------------------------------')
    print('\n'.join(transitions_log))
    print(f'{len(transitions_log)} transitions tested.\n')


def modify_and_check(udm, ldap_base, dn, disabled_state, locked_state):
    print(f'*** disabled_state={disabled_state!r} locked_state={locked_state!r}')
    if dn:
        locked = {}
        if locked_state == '0':
            locked['locked'] = '0'
        udm.modify_object('users/user', dn=dn, disabled=disabled_state, **locked)
        if locked_state == '1':
            locktime = time.strftime("%Y%m%d%H%M%SZ", time.gmtime())
            subprocess.call(['python3', '-m', 'univention.lib.account', 'lock', '--dn', dn, '--lock-time', locktime])
    else:
        dn, _username = udm.create_user(
            position=f'cn=users,{ldap_base}',
            disabled=disabled_state,
        )
        if locked_state == '1':
            locktime = time.strftime("%Y%m%d%H%M%SZ", time.gmtime())
            subprocess.call(['python3', '-m', 'univention.lib.account', 'lock', '--dn', dn, '--lock-time', locktime])

    krb_state = b'254' if disabled_state == '1' or 'kerberos' in disabled_state else b'126'
    smb_disabled = disabled_state == '1' or 'windows' in disabled_state
    smb_locked = locked_state in ('1')
    if transitions_log:
        transitions_log[-1] += f' -> {disabled_state:16} | {locked_state:8}'

    # length of whitespace in sambaAcctFlags varies. cannot use utils.verify_ldap_object() to test it

    lo, _pos = univention.admin.uldap.getMachineConnection(ldap_master=False)
    user = lo.get(dn)
    print_transitions()
    assert user['krb5KDCFlags'] == [krb_state], 'krb5KDCFlags: expected {!r} found {!r}'.format(krb_state, user['krb5KDCFlags'])
    assert not (smb_disabled and b'D' not in user['sambaAcctFlags'][0]), 'sambaAcctFlags: expected D in flags, found {!r}'.format(user['sambaAcctFlags'])
    assert not ((smb_locked and not smb_disabled) and b'L' not in user['sambaAcctFlags'][0]), 'sambaAcctFlags: expected L in flags, found {!r}'.format(user['sambaAcctFlags'])
    assert not ((smb_locked and smb_disabled) and b'L' in user['sambaAcctFlags'][0]), 'sambaAcctFlags: unexpected L in flags: {!r}'.format(user['sambaAcctFlags'])
    assert not ((disabled_state == '1' or 'posix' in disabled_state) and user['shadowExpire'][0] != b'1'), 'shadowExpire: expected {!r} found {!r}'.format(['1'], user['shadowExpire'])
    print('*** OK.')
    if transitions_log:
        transitions_log[-1] = f'OK: {transitions_log[-1]}'
    transitions_log.append(f'{disabled_state:16} | {locked_state:8}')
    return dn
