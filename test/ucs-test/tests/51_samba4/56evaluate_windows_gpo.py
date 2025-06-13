#!/usr/share/ucs-test/runner python3
## desc: Test if GPOs created on a native Windows Server work with S4
## exposure: dangerous
## packages: [univention-samba4, ucs-windows-tools]
## tags: [basic, windows_gpo_test, native_win_client, SKIP]
## bugs: [37568]
## roles:
## - domaincontroller_master
## - domaincontroller_slave

import xml.etree.ElementTree as ET  # noqa: S405
from os import path
from re import search
from subprocess import PIPE, Popen
from sys import exit

import univention.winexe
from univention.config_registry import ConfigRegistry
from univention.testing import utils
from univention.testing.codes import Reason
from univention.testing.strings import random_username
from univention.testing.ucs_samba import force_drs_replication
from univention.testing.udm import UCSTestUDM


def run_cmd(cmd, stdout=PIPE, stdin=None, std_in=None, encoding='UTF-8'):
    """
    Creates a process as a Popen instance with a given 'cmd'
    and 'communicates' with it.
    """
    proc = Popen(cmd, stdout=stdout, stderr=PIPE, stdin=stdin)
    stdout, stderr = proc.communicate(std_in)
    return stdout.decode(encoding), stderr.decode(encoding)


def remove_samba_warnings(input_str):
    """Removes the Samba Warning/Note from the given input_str."""
    # ignoring following messages (Bug #37362):
    input_str = input_str.replace('WARNING: No path in service IPC$ - making it unavailable!', '')
    return input_str.replace('NOTE: Service IPC$ is flagged unavailable.', '').strip()


def run_samba_tool(cmd, stdout=PIPE):
    """
    Creates a process as a Popen instance with a given 'cmd'
    and 'communicates' with it. Adds samba credintials to cmd.
    Returns (stdout, stderr).
    """
    cmd += samba_credentials
    stdout, stderr = run_cmd(cmd)

    if stderr:
        stderr = remove_samba_warnings(stderr)
    if stdout:
        stdout = remove_samba_warnings(stdout)
    return stdout, stderr


def samba_create_test_user():
    """Creates a 'test_username' via samba-tool."""
    print("\nCreating a '%s' user for the test." % test_username)
    cmd = ("samba-tool", "user", "create", test_username, "Univention@99", "--given-name=" + test_username)

    stdout, stderr = run_samba_tool(cmd)
    if stderr:
        print("An error/warning occurred while trying to create a user with a username '%s' via command: '%s' \nSTDERR: %s" % (test_username, " ".join(cmd), stderr))
    if stdout:
        print(stdout)


def windows_create_gpo(gpo_name, gpo_comment, server=""):
    """
    Creates a GPO with a given 'gpo_name' and 'gpo_comment' via
    winexe running the powershell script on the Windows host.
    """
    print("\nCreating GPO for the test with a name:", gpo_name)
    try:
        ret_code, stdout, stderr = Win.create_gpo(gpo_name, gpo_comment, server)
        if ret_code != 0:
            utils.fail("The creation of the GPO on the Windows host returned code '%s' when 0 is expected. STDOUT: %s STDERR: %s" % (ret_code, stdout, stderr))
    except univention.winexe.WinExeFailed as exc:
        utils.fail("An Error occurred while creating GPO remotely: %r" % exc)


def windows_link_gpo(gpo_name, container, server=""):
    """
    Links a given 'gpo_name' to a container using powershell script
    on Windows Host via winexe.
    """
    print("\nLinking GPO '%s' to a '%s'" % (gpo_name, container))
    try:
        ret_code, stdout, stderr = Win.link_gpo(
            gpo_name, 1, container, server)
        if ret_code != 0:
            utils.fail("The linking of the GPO on the Windows host returned code '%s' when 0 is expected. STDOUT: %s STDERR: %s" % (ret_code, stdout, stderr))
    except univention.winexe.WinExeFailed as exc:
        utils.fail("An Error occurred while linking a GPO remotely: %r" % exc)


def windows_force_gpo_update():
    print("Forcing GPO update on Windows:")
    try:
        _ret_code, stdout, stderr = Win.force_gpo_update()
        if stdout:
            print(stdout)
        if stderr:
            print(stderr)
    except univention.winexe.WinExeFailed as exc:
        utils.fail("An Error occurred while linking a GPO remotely: %r" % exc)


def windows_set_gpo_security_filter(gpo_name, permission_level, target_name, target_type, replace="False", server=""):
    """
    Applies the 'gpo_name' GPO to the 'target_name' of the 'target_type'
    by executing a powershell script on Windows host via winexe.
    By default (server="") the powershell code will select
    the Master (fsmo: PDC emulator) to run against.
    """
    if permission_level not in ("GpoRead", "GpoApply", "GpoEdit", "GpoEditDeleteModifySecurity", "None"):
        utils.fail("Set-GPPermissions: unsupported permission_level: %s" % permission_level)

    if target_type not in ("Computer", "User", "Group"):
        utils.fail("Set-GPPermissions: unsupported target_type: %s" % target_type)

    print("\nSet-GPPermissions on '%s' for '%s' '%s' to '%s'" % (gpo_name, target_name, target_type, permission_level))
    try:
        ret_code, stdout, stderr = Win.Set_GPPermissions(
            gpo_name,
            permission_level,
            target_name,
            target_type,
            replace,
            server)
        if ret_code != 0:
            utils.fail("Set-GPPermissions on the Windows host returned status '%s' when 0 is expected. STDOUT: %s STDERR: %s" % (ret_code, stdout, stderr))
    except univention.winexe.WinExeFailed as exc:
        utils.fail("Exception during Set-GPPermissions: %r" % exc)


def samba_check_gpo_exists(gpo_name):
    """Checks that GPO with 'gpo_name' exists via samba-tool."""
    print("\nChecking that GPO '%s' exists." % gpo_name)
    cmd = ("samba-tool", "gpo", "listall")

    stdout, _stderr = run_samba_tool(cmd)
    if not stdout:
        utils.fail("The samba-tool did not produce any output when list of all GPOs is expected.")
    if gpo_name not in stdout:
        utils.fail("The GPO '%s' was not found in the list of all GPOs." % gpo_name)


def windows_set_gpo_registry_value(gpo_name, reg_key, value_name, value, value_type, server=""):
    """
    Sets the 'value_name', 'value' and 'value_type' for 'gpo_name' Registry Key
    By default (server="") the powershell code will select
    the Master (fsmo: PDC emulator) to run against.
    """
    print("\nModifying the '%s' GPO '%s' registry key " % (gpo_name, reg_key))
    try:
        ret_code, stdout, stderr = Win.Set_GPRegistryValue(
            gpo_name,
            reg_key,
            value_name,
            value,
            value_type,
            server)
        if ret_code != 0:
            utils.fail("The modification of the GPO on the Windows host returned code '%s' when 0 is expected. STDOUT: %s STDERR: %s" % (ret_code, stdout, stderr))
    except univention.winexe.WinExeFailed as exc:
        utils.fail("An Error occurred while modifying GPO remotely: %r" % exc)


def samba_get_gpo_uid_by_name(gpo_name):
    """Returns the {GPO UID} for the given gpo_name using samba-tool."""
    stdout, stderr = run_samba_tool(("samba-tool", "gpo", "listall"))
    if not stdout:
        utils.fail("The samba-tool did not produce any output when list of all GPOs is expected.")
    if stderr:
        print("Samba-tool STDERR:", stderr)

    stdout = stdout.split('\n\n')  # separate GPOs
    for gpo in stdout:
        if gpo_name in gpo:
            return '{' + search('{(.+?)}', gpo).group(1) + '}'


def windows_check_gpo_report(gpo_name, identity_name, server=""):
    """
    Gets the XML GPOreport for the 'gpo_name' from the remote Windows Host
    via winexe. Checks that 'identity_name' has 'gpo_name' applied.
    """
    print("\nCollecting and checking the GPOreport for %s:" % gpo_name)
    try:
        ret_code, stdout, stderr = Win.get_gpo_report(gpo_name, server)
        if ret_code != 0:
            utils.fail("The collection of the GPO report on the Windows host returned code '%s' when 0 is expected. STDOUT: %s STDERR: %s" % (ret_code, stdout, stderr))
        if not stdout:
            utils.fail("The GPOreport STDOUT from the remote Windows Host is empty.")
        if stderr:
            print("\nGET-GPOreport STDERR:", stderr)
    except univention.winexe.WinExeFailed as exc:
        utils.fail("An Error occurred while collecting GPO report remotely: %r" % exc)

    # Recode to match encoding specified in XML header
    gporeport_unicode = stdout.decode('cp850')
    gporeport_utf16 = gporeport_unicode.encode('utf-16')

    gpo_root = ET.fromstring(gporeport_utf16)  # noqa: S314
    gpo_types = "http://www.microsoft.com/GroupPolicy/Types"

    # find the 'TrusteePermissions' tags in xml:
    for trust_perm in gpo_root.iter("{%s/Security}TrusteePermissions" % gpo_types):

        # check name tag of the 'Trustee':
        for name in trust_perm.iter("{%s}Name" % gpo_types):
            trustee = name.text.split('\\', 1)[-1]  # cut off netbios domain prefix
            if identity_name == trustee:
                print("Found GPO test identity '%s'." % identity_name)

                # check GPO is applied to user/computer:
                for access in trust_perm.iter("{%s/Security}GPOGroupedAccessEnum" % gpo_types):
                    if "Apply Group Policy" in access.text:
                        print("Confirmed '%s' GPO application to '%s'." % (gpo_name, identity_name))
                        return True

    print("\nUnexpected GPOreport:\n")
    print(gporeport_unicode)
    utils.fail("\nCould not confirm that GPO '%s' is applied to '%s'" % (gpo_name, identity_name))


def sysvol_sync():
    """
    We need to sync the sysvol from the master (fsmo: PDC emulator)
    because the special Domain DFS module dfs_server/dfs_server_ad.c
    randomizes the DFS referral for the Windows client
    """
    stdout, stderr = run_cmd("/usr/share/univention-samba4/scripts/sysvol-sync.sh")
    print(stdout)
    if stderr:
        print("\nAn Error occurred during sysvol sync:", stderr)


def sysvol_check_gpo_registry_value(gpo_name, reg_key, value_name, value):
    """
    Checks that GPO exists on the filesystem level in sysvol;
    Checks the Registry.pol contents has test values.
    """
    print("\nChecking '%s' GPO registry key value in Samba" % gpo_name)
    gpo_uid = samba_get_gpo_uid_by_name(gpo_name)  # get GPO UID to determine path

    gpo_path = '/var/lib/samba/sysvol/%s/Policies/%s' % (domainname, gpo_uid)
    if not path.exists(gpo_path):
        utils.fail("The location of '%s' GPO cannot be found at '%s'" % (gpo_name, gpo_path))

    if (not path.exists(gpo_path + '/Machine') or not path.exists(gpo_path + '/User')):
        # both folders should exist
        utils.fail("The '%s' GPO has no Machine or User folder at '%s'" % (gpo_name, gpo_path))

    if reg_key.startswith('HKCU'):
        reg_pol_file = gpo_path + '/User/Registry.pol'
    elif reg_key.startswith('HKLM'):
        reg_pol_file = gpo_path + '/Machine/Registry.pol'
    else:
        utils.fail("The given registry key '%s' should be either HKCU or HKLM" % reg_key)

    if not path.exists(reg_pol_file):
        utils.fail("The Registry.pol file cannot be found at '%s'" % reg_pol_file)

    try:
        reg_policy = open(reg_pol_file)
        # skip first 8 bytes (signature and file version):
        # https://msdn.microsoft.com/en-us/library/aa374407%28v=vs.85%29.aspx
        reg_policy_text = reg_policy.read()[8:].decode(encoding='utf-16')
        reg_policy.close()
    except OSError as exc:
        utils.fail("An Error occurred while opening '%s' file: %r" % (reg_pol_file, exc))

    reg_key = reg_key[5:]  # the 'HKCU\' or 'HKLM\' are not included:
    if reg_key not in reg_policy_text:
        utils.fail("Could not find '%s' Registry key in '%s' GPO Registry.pol" % (reg_key, gpo_name))

    if value_name not in reg_policy_text:
        utils.fail("Could not find '%s' ValueName in '%s' GPO Registry.pol" % (value_name, gpo_name))

    if value not in reg_policy_text:
        utils.fail("Could not find '%s' Value in '%s' GPO Registry.pol" % (value, gpo_name))


def samba_check_gpo_application_listed(gpo_name, username):
    """
    Checks if the 'gpo_name' GPO is listen in GPOs for
    'username' via samba-tool.
    """
    print("\nChecking that GPO '%s' is applied to %s" % (gpo_name, username))
    stdout, stderr = run_samba_tool(("samba-tool", "gpo", "list", username))
    if stdout:
        print(stdout)
    if stderr:
        print(stderr)

    if not stdout:
        utils.fail("The samba-tool did not produce any output when list of all user/computer GPOs is expected.")
    if gpo_name not in stdout:
        utils.fail("The GPO '%s' was not found in the list of all user/computer GPOs." % gpo_name)


def dns_get_host_ip(host_name, all=False):
    """Lookup host_name;"""
    print("\nLooking for '%s' host ip address:" % host_name)

    ips = []
    dig_sources = []
    for source in ['nameserver1', 'nameserver2', 'nameserver3']:
        if source in ucr:
            dig_sources.append("@%s" % ucr[source])

    for dig_source in dig_sources:
        try:
            cmd = ['dig', dig_source, host_name, '+search', '+short']
            p1 = Popen(cmd, close_fds=True, stdout=PIPE, stderr=PIPE)
            stdout, _stderr = p1.communicate()
            if p1.returncode == 0:
                for i in stdout.split('\n'):
                    if i:
                        ips.append(i)
            if ips:
                break
        except OSError as ex:
            print("\n%s failed: %s" % (cmd, ex.args[1]))

    if not ips:
        utils.fail("Could not resolve '%s' via DNS." % host_name)
    else:
        if all:
            print("Host IPs are: %s" % (ips,))
            return ips
        else:
            print("Host IP is: %s" % (ips[0],))
            return ips[0]


def udm_get_windows_computer():
    """
    Using UDM looks for 'computers/windows' hostname of the joined
    Windows Host (Assuming there is only one).
    """
    stdout, stderr = run_cmd(("udm", "computers/windows", "list"))
    if stderr:
        print("\nAn Error occurred while looking for Windows Server hostname:", stderr)

    sed_stdout, stderr = run_cmd(("sed", "-n", "s/^DN: //p"), stdin=PIPE, std_in=stdout)
    if not sed_stdout:
        print("SKIP: failed to find any Windows Host DN via UDM. Perhaps host not joined as a memberserver or does not exist in this setup.")
        exit(Reason.INSTALL)

    return {'hostdn': sed_stdout, 'hostname': sed_stdout.split(',')[0][3:]}


def windows_check_domain():
    """Runs powershell script via Winexe to check Windows Host domain is correct."""
    print("Trying to check Windows host '%s' domain" % Win.client)
    try:
        Win.winexec("check-domain", domainname)
    except univention.winexe.WinExeFailed as exc:
        utils.fail("Failed to check that Windows host domain is correct: %r" % exc)


def samba_remove_test_user():
    """Removes 'the test_username' via samba-tool."""
    print("\nRemoving '%s' user:" % test_username)
    stdout, stderr = run_samba_tool(("samba-tool", "user", "delete", test_username))
    if stdout:
        print(stdout)
    if stderr:
        print(stderr)


def windows_remove_test_gpo(gpo_name, server=""):
    """
    Removes the GPO with a given 'gpo_name' via
    winexe running the powershell script on the Windows host.
    """
    print("\nRemoving GPOs created for the test:", gpo_name)
    try:
        ret_code, stdout, stderr = Win.remove_gpo(gpo_name, server)
        if ret_code != 0:
            print("The removal of the GPO on the Windows host returned code '%s' when 0 is expected. STDOUT: %s STDERR: %s" % (ret_code, stdout, stderr))
    except (univention.winexe.WinExeFailed, NameError) as exc:
        print("An Error occurred while removing GPO remotely: %r" % exc)


if __name__ == '__main__':
    """
    IMPORTANT: Windows Host should be joined to the domain prior test run!

    Finds Windows hostname and ip;
    Configures Winexe and checks win domain;
    Creates a User via samba-tool;
    Creates a GPO on the remote Windows Host (joined into Domain);
    Checks created GPO exist via samba-tool;
    Applies the GPO to the User and modifies GPO registry values;
    Checks GPO is listed by samba-tool for the User;
    Checks GPO registry values in the samba sysvol;
    Gets GPO report from Windows Host and verifies GPO application.

    Performs similar checks for Machine GPO using Windows host account.

    GPOs are applied using 'Security Filtering',
    'Authenticated Users' are set to have only GpoRead permissions.
    """
    ucr = ConfigRegistry()
    ucr.load()

    domain_admin_dn = ucr.get('tests/domainadmin/account')
    domain_admin_password = ucr.get('tests/domainadmin/pwd')
    windows_admin = ucr.get('tests/windowsadmin/account', 'Administrator')
    windows_admin_password = ucr.get('tests/windowsadmin/pwd', 'univention')
    domainname = ucr.get('domainname')
    hostname = ucr.get('hostname')
    ldap_base = ucr.get('ldap/base')

    if not all((domain_admin_dn, domain_admin_password, domainname, hostname, ldap_base)):
        print("\nFailed to obtain settings for the test from UCR. Skipping the test.")
        exit(Reason.INSTALL)

    domain_admin = domain_admin_dn.split(',')[0][len('uid='):]
    samba_credentials = ("--username=" + domain_admin, "--password=" + domain_admin_password)

    windows_client = udm_get_windows_computer()

    # setup winexe:
    Win = univention.winexe.WinExe(
        domainname,
        domain_admin, domain_admin_password,
        windows_admin, windows_admin_password,
        445, dns_get_host_ip(windows_client['hostname']), loglevel=4)
    windows_check_domain()

    test_username = 'ucs_test_gpo_user_' + random_username(4)
    random_gpo_suffix = random_username(4)
    test_user_gpo = 'test_user_gpo_' + random_gpo_suffix
    test_machine_gpo = 'test_machine_gpo_' + random_gpo_suffix

    UDM = UCSTestUDM()
    test_user_dn = UDM.create_user(
        username=test_username,
        password='univention',
    )[0]

    try:
        # case 1: checks with user GPO
        gpo_name = test_user_gpo
        windows_create_gpo(gpo_name, "GPO for %s" % (test_username,))
        force_drs_replication()
        force_drs_replication(direction="out")
        samba_check_gpo_exists(gpo_name)

        sysvol_sync()
        windows_set_gpo_registry_value(
            gpo_name,
            r"HKCU\Software\Policies\Microsoft\UCSTestKey",
            "TestUserValueOne",
            "Foo",
            "String")
        force_drs_replication()
        force_drs_replication(direction="out")
        sysvol_sync()
        sysvol_check_gpo_registry_value(
            gpo_name,
            r"HKCU\Software\Policies\Microsoft\UCSTestKey",
            "TestUserValueOne",
            "Foo")

        windows_link_gpo(gpo_name, ldap_base)
        force_drs_replication()
        force_drs_replication(direction="out")
        samba_check_gpo_application_listed(gpo_name, test_username)

        windows_set_gpo_security_filter(gpo_name, 'GpoRead', 'Authenticated Users', 'Group', 'True')
        if ucr.is_true("connector/s4/mapping/gpo/ntsd", False):
            # Workaround for Bug #35336
            utils.wait_for_connector_replication()
            utils.wait_for_replication()
            utils.wait_for_connector_replication()
        windows_set_gpo_security_filter(gpo_name, 'GpoApply', test_username, 'User')
        force_drs_replication()
        force_drs_replication(direction="out")
        windows_force_gpo_update()
        windows_check_gpo_report(gpo_name, test_username)

        # case 2: checks with computer GPO
        gpo_name = test_machine_gpo
        windows_create_gpo(gpo_name, "GPO for %s Windows host" % windows_client['hostname'])
        force_drs_replication()
        force_drs_replication(direction="out")
        samba_check_gpo_exists(gpo_name)

        sysvol_sync()
        windows_set_gpo_registry_value(
            gpo_name,
            r"HKLM\Software\Policies\Microsoft\UCSTestKey",
            "TestComputerValueTwo",
            "Bar",
            "String")
        force_drs_replication()
        force_drs_replication(direction="out")
        sysvol_sync()
        sysvol_check_gpo_registry_value(
            gpo_name,
            r"HKLM\Software\Policies\Microsoft\UCSTestKey",
            "TestComputerValueTwo",
            "Bar")

        windows_link_gpo(gpo_name, ldap_base)
        force_drs_replication()
        force_drs_replication(direction="out")
        samba_check_gpo_application_listed(gpo_name, windows_client['hostname'])

        windows_set_gpo_security_filter(gpo_name, 'GpoRead', 'Authenticated Users', 'Group', 'True')
        if ucr.is_true("connector/s4/mapping/gpo/ntsd", False):
            # Workaround for Bug #35336
            utils.wait_for_connector_replication()
            utils.wait_for_replication()
            utils.wait_for_connector_replication()
        windows_set_gpo_security_filter(gpo_name, 'GpoApply', windows_client['hostname'], 'Computer')
        force_drs_replication()
        force_drs_replication(direction="out")
        windows_force_gpo_update()
        windows_check_gpo_report(gpo_name, "%s$" % windows_client['hostname'])
    finally:
        windows_remove_test_gpo(test_user_gpo)
        windows_remove_test_gpo(test_machine_gpo)
        UDM.remove_object('users/user', dn=test_user_dn)
