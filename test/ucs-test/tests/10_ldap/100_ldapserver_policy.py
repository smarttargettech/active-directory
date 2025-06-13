#!/usr/share/ucs-test/runner python3
## desc: Test creation/modification of LDAP server / UCR policy for LDAP server
## exposure: dangerous
## packages:
##  - univention-ldap-server
##  - python3-univention-directory-manager
## roles:
##  - domaincontroller_master
##  - domaincontroller_backup
## tags:
##  - skip_admember

import univention.admin.modules as udm_modules
import univention.admin.objects
import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils
from univention.testing.udm_extensions import call_cmd


with ucr_test.UCSTestConfigRegistry() as ucr:
    domain = ucr.get("domainname")
    basedn = ucr.get("ldap/base")
    admin_dn = ucr.get("tests/domainadmin/account")
    admin_pw_file = ucr.get("tests/domainadmin/pwdfile")

lo = utils.get_ldap_connection(admin_uldap=True)
univention.admin.modules.update()
admin_user = None


def get_admin_user():
    filter_s = admin_dn.partition(",")[0]
    base_s = admin_dn.partition(",")[-1]
    admin_user = udm_modules.lookup("users/user", None, lo, base=base_s, scope="sub", filter=filter_s)[0]
    admin_user.open()
    return admin_user["username"]


def check_all_servers_in_policies(ldap_servers, udm_backups):
    ldapserver_policies = udm_modules.lookup("policies/ldapserver", None, lo, base=basedn, scope="sub", filter="(cn=default-settings)")
    ldapserver_policy = ldapserver_policies[0]

    if not all(map(lambda x: x in ldapserver_policy["ldapServer"], ldap_servers)):
        utils.fail(
            "LDAP server policy does not contain all DC master and DC "
            "backups. ldapserver_policy[ldapServer]: {} ldap_servers: {}".format(ldapserver_policy["ldapServer"], ldap_servers),
        )

    registry_policies = udm_modules.lookup("policies/registry", None, lo, base=basedn, scope="sub", filter="(cn=default-ldap-servers)")
    registry_policy = registry_policies[0]

    ucr_backups = []
    for ucr in registry_policy["registry"]:
        if ucr[0] == "ldap/server/addition":
            ucr_backups = ucr[1].split()

    if not all(map(lambda x: x in ucr_backups, udm_backups)):
        utils.fail(f"UCR policy does not contain all DC backups. ucr_backups: {ucr_backups} udm_backups: {udm_backups}")


def situation_before_test():
    dc_masters = udm_modules.lookup("computers/domaincontroller_master", None, lo, base=basedn, scope="sub")
    dc_backups = udm_modules.lookup("computers/domaincontroller_backup", None, lo, base=basedn, scope="sub")
    ldap_servers = []
    for master in dc_masters:
        master.open()
        if master["fqdn"]:
            ldap_servers.append(master["fqdn"])
    for backup in dc_backups:
        backup.open()
        if backup["fqdn"]:
            ldap_servers.append(backup["fqdn"])
    udm_backups = [b["fqdn"] for b in dc_backups if b["fqdn"]]

    return ldap_servers, udm_backups


def run_join_script():
    global admin_user
    if not admin_user:
        admin_user = get_admin_user()

    call_cmd([
        "univention-run-join-scripts",
        "-dcaccount", admin_user,
        "-dcpwd", admin_pw_file,
        "--force",
        "--run-scripts",
        "10univention-ldap-server.inst"],
    )


def add_dc_backup(udm):
    name = uts.random_name()
    fqdn = f"{name}.{domain}"

    udm.create_object(
        'computers/domaincontroller_backup',
        set={
            "position": f"cn=dc,cn=computers,{basedn}",
            "name": name,
            "domain": domain,
        },
    )
    run_join_script()

    return fqdn


def main():
    print("** Running checks on situation before test...")
    ldap_servers, udm_backups = situation_before_test()
    check_all_servers_in_policies(ldap_servers, udm_backups)

    with udm_test.UCSTestUDM() as udm:
        print("** Adding a DC backup...")
        fqdn = add_dc_backup(udm)

        ldap_servers.append(fqdn)
        udm_backups.append(fqdn)
        check_all_servers_in_policies(ldap_servers, udm_backups)

        print("** Adding another DC backup...")
        fqdn = add_dc_backup(udm)

        ldap_servers.append(fqdn)
        udm_backups.append(fqdn)
        check_all_servers_in_policies(ldap_servers, udm_backups)

        print("** Removing both test DC backups...")
        # by leaving the context manager
    utils.wait_for_replication()

    run_join_script()

    ldap_servers.pop()
    ldap_servers.pop()
    udm_backups.pop()
    udm_backups.pop()
    check_all_servers_in_policies(ldap_servers, udm_backups)


if __name__ == '__main__':
    main()
