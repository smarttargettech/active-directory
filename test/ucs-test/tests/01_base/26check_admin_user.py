#!/usr/share/ucs-test/runner python3
## desc: Check if 'Administrator' is in the right Groups and respective SIDs
## roles-not: [basesystem]
## bugs: [37331]
## tags: [basic, apptest]
## exposure: safe

from subprocess import PIPE, Popen

from univention.config_registry import ConfigRegistry
from univention.testing import utils


UCR = ConfigRegistry()
UCR.load()

errors = 0


def increase_errors_counter():
    """Increments the global 'errors' counter."""
    global errors
    errors += 1


def check_user_groups_sids():
    """
    Checks that 'test_username' and 'test_groups' have correct SIDs
    when applicable.
    """
    print("\nChecking SIDs where applicable:")

    # following SIDs should be 'S-1-5-21-' + domainSID + specific ending
    sid_check_dict = {"uid=" + test_username: "-500",  # Administrator
                      "cn=" + test_groups[0]: "-512",  # Domain Admin
                      "cn=" + test_groups[1]: "-513"}  # Domain Users
    # more on well-known-sids: http://support.microsoft.com/kb/243330/en-us

    for key, sid_ending in sid_check_dict.items():
        sid_in_ldap = get_sid_for_user_group(key)
        if not sid_in_ldap:
            utils.fail("The 'sambaSID' for '%s' is empty." % key)

        print("\nRecord:", key)
        print("SID:", sid_in_ldap)

        if not (sid_in_ldap.startswith('S-1-5-21-') and sid_in_ldap.endswith(sid_ending)):
            print("\nThe SID '%s' for '%s' is incorrect. Expected to start "
                  "with 'S-1-5-21-' and to end with '%s'"
                  % (sid_in_ldap, key, sid_ending))
            increase_errors_counter()


def check_user_in_groups():
    """Checks if 'test_username' user is a member of test_groups."""
    print("\nChecking group members:")

    for group in test_groups:
        if test_username not in get_members_in_group(group):
            print(f"\nFAIL: the '{test_username}' user is not a member of the '{group}' group.\n")
            increase_errors_counter()


def get_localized_translations():
    """
    Returns the Administrator username and groups in localazed translation
    or in English if there are no translations found in the UCR.
    """
    print("Determining Administrator username and group translations if any.")

    # Administrator username translation:
    translated_username = UCR.get('users/default/administrator') or "Administrator"

    # the UCR vars for groups translation:
    ucr_translations = ('domainadmins', 'domainusers', 'windowshosts',
                        'dcbackuphosts', 'dcslavehosts', 'computers')

    # respective default English names:
    default_english = ("Domain Admins", "Domain Users", "Windows Hosts",
                       "DC Backup Hosts", "DC Slave Hosts", "Computers")

    translated_groups = []

    for num, val in enumerate(ucr_translations):
        # get a translation or pick a default English name:
        translated_groups.append(UCR.get('groups/default/' + val, default_english[num]))

    return translated_username, translated_groups


def create_and_run_process(cmd, stdin=None, std_input=None, shell=False, stdout=PIPE):
    """
    Creates a process as a Popen instance with a given 'cmd'
    and executes it. When stdin is needed, it can be provided as kwarg.
    To write to a file an istance can be provided to stdout.
    """
    proc = Popen(cmd, stdin=stdin, stdout=stdout, stderr=PIPE, shell=shell, close_fds=True)
    return proc.communicate(input=std_input)


def get_sid_for_user_group(name):
    """
    Returns a SID for a given 'name'.
    Name should include the uid=... or cn=...
    """
    stdout, stderr = create_and_run_process(('univention-ldapsearch', name))

    if stderr:
        print("\nThe following message occurred in stderr:", stderr.decode('UTF-8', 'replace'))

    sed_stdout, sed_stderr = create_and_run_process(("sed", "-n", "s/^sambaSID: //p"), PIPE, stdout)

    if sed_stderr:
        print("\nThe following message occurred in stderr:", sed_stderr.decode('UTF-8', 'replace'))

    return sed_stdout.decode('UTF-8').strip('\n')


def get_members_in_group(group_name):
    """Returns a list of members as found via 'getent' for a given 'group_name'."""
    cmd = ('getent', 'group', group_name)
    stdout, stderr = create_and_run_process(cmd)

    if stderr:
        print("\nThe following message occurred in stderr while using 'getent':")
        print(stderr.decode('UTF-8', 'replace'))

    stdout = stdout.strip().decode('UTF-8')
    if not stdout:
        print("\nNo stdout from 'getent' for a '%s' group." % group_name)
        return []

    # remove the group name, password, gid and separate members by commas:
    members = stdout[(stdout.rfind(':') + 1):].split(',')

    print("\nGroup:", group_name)
    print("Members of the group:", members)
    return members


if __name__ == '__main__':
    """
    Get Administrator and Groups translations in case of a non-english AD;
    Check that Administrator is a member of specific Groups;
    Check SIDs for Administrator and groups where applicable.
    """
    test_username, test_groups = get_localized_translations()
    print("\nUser name to be tested:", test_username)
    print(f"Groups where {test_username} should be a member: {test_groups}")

    check_user_in_groups()
    check_user_groups_sids()

    if errors:
        utils.fail("There were %d error(s) detected during the test execution."
                   " Please check the complete test output." % errors)
