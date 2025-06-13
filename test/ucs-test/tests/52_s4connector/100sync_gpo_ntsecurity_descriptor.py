#!/usr/share/ucs-test/runner python3
## desc: "GPO Security Descriptor sync"
## exposure: dangerous
## packages:
##   - univention-config
##   - univention-directory-manager-tools
##   - univention-samba4
##   - univention-s4-connector
## tags:
##   - performance
## bugs:
##   - 33768

import re
import subprocess
import time

import ldb
from ldap.filter import filter_format
from samba.auth import system_session
from samba.credentials import Credentials
from samba.dcerpc import security
from samba.ndr import ndr_unpack
from samba.param import LoadParm
from samba.samdb import SamDB
from samba.sd_utils import SDUtils

import univention.testing.udm as udm_test
import univention.uldap
from univention.config_registry import ConfigRegistry
from univention.s4connector import configdb
from univention.testing import utils
from univention.testing.strings import random_username

import s4connector


def set_ucr(ucr_set, ucr_unset=None, ucr=None):
    if not ucr:
        ucr = ConfigRegistry()
        ucr.load()

    previous_ucr_set = []
    previous_ucr_unset = []

    if ucr_set:
        if isinstance(ucr_set, str):
            ucr_set = (ucr_set,)

        for setting in ucr_set:
            var = setting.split("=", 1)[0]
            new_val = setting.split("=", 1)[1]
            old_val = ucr.get(var)
            if new_val == old_val:
                continue

            if old_val is not None:
                previous_ucr_set.append('%s=%s' % (var, old_val))
            else:
                previous_ucr_unset.append('%s' % (var,))

        univention.config_registry.handler_set(ucr_set)

    if ucr_unset:
        if isinstance(ucr_unset, str):
            ucr_unset = (ucr_unset,)

        for var in ucr_unset:
            val = ucr.get(var)
            if val is not None:
                previous_ucr_set.append('%s=%s' % (var, val))

        univention.config_registry.handler_unset(ucr_unset)

    return (previous_ucr_set, previous_ucr_unset)


class Testclass_GPO_Security_Descriptor:

    def __init__(self, udm, ucr=None):
        self.SAM_LDAP_FILTER_GPO = "(&(objectclass=grouppolicycontainer)(cn=%s))"
        self.gpo_ldap_filter = None
        self.gponame = None

        self.udm = udm

        if ucr:
            self.ucr = ucr
        else:
            self.ucr = ConfigRegistry()
            self.ucr.load()

        self.adminaccount = utils.UCSTestDomainAdminCredentials()
        self.machine_ucs_ldap = univention.uldap.getMachineConnection()

        self.fqdn = ".".join((self.ucr["hostname"], self.ucr["domainname"]))

        self.lp = LoadParm()
        self.lp.load_default()

        self.samba_machine_creds = Credentials()
        self.samba_machine_creds.guess(self.lp)
        self.samba_machine_creds.set_machine_account(self.lp)
        self.machine_samdb = SamDB(url="/var/lib/samba/private/sam.ldb", session_info=system_session(), credentials=self.samba_machine_creds, lp=self.lp)
        self.domain_sid = security.dom_sid(self.machine_samdb.get_domain_sid())
        self.DA_SID = security.dom_sid("%s-%d" % (self.domain_sid, security.DOMAIN_RID_ADMINS))
        self.DU_SID = security.dom_sid("%s-%d" % (self.domain_sid, security.DOMAIN_RID_USERS))

        self.samba_admin_creds = Credentials()
        self.samba_admin_creds.guess(self.lp)
        self.samba_admin_creds.parse_string(self.adminaccount.username)
        self.samba_admin_creds.set_password(self.adminaccount.bindpw)
        self.admin_samdb = SamDB(url="/var/lib/samba/private/sam.ldb", session_info=system_session(), credentials=self.samba_admin_creds, lp=self.lp)
        self.admin_samdb_sdutil = SDUtils(self.admin_samdb)

    def restart_s4_connector(self):
        cmd = ("/etc/init.d/univention-s4-connector", "restart")
        p1 = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, close_fds=True)
        stdout, _stderr = p1.communicate()
        if p1.returncode != 0:
            utils.fail("Error restarting S4 Connector: %s\nCommand was: %s" % (stdout.decode('UTF-8', 'replace'), cmd))

    def activate_ntsd_sync(self):
        ucr_set = ["connector/s4/mapping/gpo/ntsd=true"]
        self.previous_ucr_set, self.previous_ucr_unset = set_ucr(ucr_set, ucr=self.ucr)
        if self.previous_ucr_unset or self.previous_ucr_set:
            self.restart_s4_connector()

    def __enter__(self):
        self.activate_ntsd_sync()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type:
            print('GPO Cleanup after exception: %s %s' % (exc_type, exc_value))
        if self.previous_ucr_unset or self.previous_ucr_set:
            set_ucr(self.previous_ucr_set, self.previous_ucr_unset, ucr=self.ucr)
            self.restart_s4_connector()
        self.remove_gpo()

    def get_ldb_object(self, dn=None, ldap_filter=None, attrs=None):
        if not attrs:
            attrs = ["*"]
        if not ldap_filter:
            ldap_filter = "(objectClass=*)"

        if dn:
            res = self.machine_samdb.search(base=dn, scope=ldb.SCOPE_BASE, expression=ldap_filter, attrs=attrs)
        else:
            res = self.machine_samdb.search(expression=ldap_filter, attrs=attrs)

        for ldb_msg in res:
            return ldb_msg

    def get_ldb_gpo(self, gponame):
        ldap_filter = filter_format(self.SAM_LDAP_FILTER_GPO, (gponame,))
        attrs = ["nTSecurityDescriptor", "uSNChanged"]
        ldb_msg = self.get_ldb_object(ldap_filter=ldap_filter, attrs=attrs)
        return ldb_msg

    def get_ntsd(self, obj):
        if isinstance(obj, ldb.Message):
            ntsd_ndr = obj["nTSecurityDescriptor"][0]
            ntsd = ndr_unpack(security.descriptor, ntsd_ndr)
        elif isinstance(obj, tuple):
            ntsd_sddl = obj[1].get("msNTSecurityDescriptor", [None])[0]
            if not ntsd_sddl:
                raise ValueError("No msNTSecurityDescriptor synchronized")
            ntsd = security.descriptor.from_sddl(ntsd_sddl.decode('ASCII'), self.domain_sid)
        elif isinstance(obj, str):
            ntsd = security.descriptor.from_sddl(obj, self.domain_sid)
        elif isinstance(obj, bytes):
            ntsd = security.descriptor.from_sddl(obj.decode('ASCII'), self.domain_sid)
        else:
            raise ValueError("General ValueError")

        return ntsd

    def assert_owner(self, ntsd, expected_sid, logtag='assert_owner'):
        if ntsd.owner_sid != expected_sid:
            utils.fail("ERROR: %s: Unexpected owner SID! Expected: %s, Found: %s" % (logtag, expected_sid, ntsd.owner_sid))

    def get_ucs_ldap_object(self, ucs_dn):
        res = self.machine_ucs_ldap.search(base=ucs_dn, scope="base", attr=["*"])
        return res[0]

    def wait_for_s4connector_sync_to_ucs(self, ldb_msg, logtag="wait_for_s4connector_sync_to_ucs"):

        usn = int(ldb_msg["uSNChanged"][0])

        configdbfile = '/etc/univention/connector/s4internal.sqlite'
        s4c_internaldb = configdb(configdbfile)

        t0 = time.monotonic()
        while int(s4c_internaldb.get("S4", "lastUSN")) < usn:
            if time.monotonic() - t0 > 120:
                utils.fail("ERROR: %s: Replication takes too long, aborting" % logtag)
            time.sleep(1)
        time.sleep(15)

    def wait_for_object_usn_change(self, ldb_msg, logtag="wait_for_object_usn_change"):

        initial_usn = int(ldb_msg["uSNChanged"][0])
        usn = initial_usn

        t0 = time.monotonic()
        while usn == initial_usn:
            time.sleep(1)
            if time.monotonic() - t0 > 120:
                utils.fail("ERROR: %s: Replication takes too long, aborting" % logtag)
            ldb_msg = self.get_ldb_object(dn=str(ldb_msg.dn), attrs=["uSNChanged"])
            usn = int(ldb_msg["uSNChanged"][0])
        time.sleep(15)

    def remove_gpo(self, critical=True):
        if self.gponame:
            cmd = (
                "samba-tool", "gpo", "del", self.gponame,
                "-k", "no",
                "-H", "ldap://%s" % (self.fqdn,),
                "--username", self.adminaccount.username,
                "--password", self.adminaccount.bindpw)

            p1 = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, close_fds=True)
            stdout, _stderr = p1.communicate()
            if p1.returncode != 0:
                if critical:
                    utils.fail("Error removing GPO using samba-tool: %s\nCommand was: %s" % (stdout.decode('UTF-8', 'replace'), cmd))
            else:
                self.gponame = None

    def create_gpo(self, logtag="create_gpo"):
        display_name = 'ucs_test_gpo_' + random_username(8)

        cmd = (
            "samba-tool", "gpo", "create", display_name,
            "-k", "no",
            "-H", "ldap://%s" % (self.fqdn,),
            "--username", self.adminaccount.username,
            "--password", self.adminaccount.bindpw)

        p1 = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, close_fds=True)
        stdout, _stderr = p1.communicate()
        if p1.returncode != 0:
            utils.fail("ERROR: %s: creating GPO using samba-tool: %s\nCommand was: %s" % (logtag, stdout.decode('UTF-8', 'replace'), cmd))

        stdout = stdout.decode('UTF-8', 'replace').rstrip()
        try:
            self.gponame = '{' + re.search('{(.+?)}', stdout).group(1) + '}'
            self.gpo_ldap_filter = filter_format(self.SAM_LDAP_FILTER_GPO, (self.gponame,))
        except AttributeError as ex:
            utils.fail("Could not find the GPO reference in the STDOUT '%s' of the 'samba-tool', error: '%s'" % (stdout, ex))

    def modify_udm_object(self, modulename, **kwargs):
        cmd = self.udm._build_udm_cmdline(modulename, 'modify', kwargs)
        child = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
        (stdout, stderr) = child.communicate()

        if child.returncode:
            raise udm_test.UCSTestUDM_ModifyUDMObjectFailed({'module': modulename, 'kwargs': kwargs, 'returncode': child.returncode, 'stdout': stdout.decode('UTF-8', 'replace'), 'stderr': stderr.decode('UTF-8', 'replace')})

    def modify_sd_on_ucs_ldap_gpo(self, ucs_dn, ucs_ntsd):
        self.modify_udm_object('container/msgpo', dn=ucs_dn, msNTSecurityDescriptor=ucs_ntsd.as_sddl())


class Testcase_GPO_Security_Descriptor_UDM_to_SAM(Testclass_GPO_Security_Descriptor):

    def run(self):
        sync_from = "UDM"
        sync_to = "SAM"
        print("GPO Security Descriptor sync from %s to %s" % (sync_from, sync_to))
        PHASE = "preparation"

        self.create_gpo(logtag=PHASE)
        print('GPO Name: %s' % self.gponame)
        ldb_msg = self.get_ldb_gpo(self.gponame)
        sam_ntsd = self.get_ntsd(ldb_msg)
        self.assert_owner(sam_ntsd, self.DA_SID, logtag=PHASE)
        self.wait_for_s4connector_sync_to_ucs(ldb_msg, logtag=PHASE)

        sam_ntsd = self.get_ntsd(ldb_msg)
        self.assert_owner(sam_ntsd, self.DA_SID, logtag=PHASE)

        # we need the exact case of the DN otherwise udm cli will fail
        temp_dn = str(ldb_msg.dn).lower().replace(self.ucr["samba4/ldap/base"].lower(), self.ucr["ldap/base"])
        ucs_dn = self.machine_ucs_ldap.searchDn(base=temp_dn, scope='base')[0]

        uldap_msg = self.get_ucs_ldap_object(ucs_dn)
        try:
            ucs_ntsd = self.get_ntsd(uldap_msg)
        except ValueError as ex:
            utils.fail("ERROR: %s: %s" % (PHASE, ex.args[0]))
        if ucs_ntsd.as_sddl() != sam_ntsd.as_sddl():
            utils.fail("ERROR: %s: NT Security descriptor differs between %s and %s" % (PHASE, sync_from, sync_to))

        PHASE = "test"

        ucs_ntsd.owner_sid = self.DU_SID
        self.modify_sd_on_ucs_ldap_gpo(ucs_dn, ucs_ntsd)

        uldap_msg = self.get_ucs_ldap_object(ucs_dn)
        try:
            ucs_ntsd = self.get_ntsd(uldap_msg)
        except ValueError as ex:
            utils.fail("ERROR: %s: %s" % (PHASE, ex.args[0]))
        self.assert_owner(ucs_ntsd, self.DU_SID, logtag=PHASE)

        self.wait_for_object_usn_change(ldb_msg, logtag=PHASE)

        ldb_msg = self.get_ldb_gpo(self.gponame)
        sam_ntsd = self.get_ntsd(ldb_msg)

        if ucs_ntsd.as_sddl() != sam_ntsd.as_sddl():
            utils.fail("ERROR: %s: NT Security descriptor not synchronized from %s to %s" % (PHASE, sync_from, sync_to))

        PHASE = "cleanup"

        ucs_ntsd.owner_sid = self.DA_SID
        self.modify_sd_on_ucs_ldap_gpo(ucs_dn, ucs_ntsd)

        uldap_msg = self.get_ucs_ldap_object(ucs_dn)
        try:
            ucs_ntsd = self.get_ntsd(uldap_msg)
        except ValueError as ex:
            utils.fail("ERROR: %s: %s" % (PHASE, ex.args[0]))
        self.assert_owner(ucs_ntsd, self.DA_SID, logtag=PHASE)

        self.wait_for_object_usn_change(ldb_msg, logtag=PHASE)
        ldb_msg = self.get_ldb_gpo(self.gponame)
        sam_ntsd = self.get_ntsd(ldb_msg)

        if ucs_ntsd.as_sddl() != sam_ntsd.as_sddl():
            utils.fail("ERROR: %s: NT Security descriptor not re-synchronized from %s to %s" % (PHASE, sync_from, sync_to))


class Testcase_GPO_Security_Descriptor_SAM_to_UDM(Testclass_GPO_Security_Descriptor):

    def run(self):
        sync_from = "SAM"
        sync_to = "UDM"
        print("GPO Security Descriptor sync from %s to %s" % (sync_from, sync_to))
        PHASE = "preparation"

        self.create_gpo(logtag=PHASE)
        print('GPO Name: %s' % self.gponame)
        ldb_msg = self.get_ldb_gpo(self.gponame)
        sam_ntsd = self.get_ntsd(ldb_msg)
        self.assert_owner(sam_ntsd, self.DA_SID, logtag=PHASE)
        self.wait_for_s4connector_sync_to_ucs(ldb_msg, logtag=PHASE)

        sam_ntsd = self.get_ntsd(ldb_msg)
        self.assert_owner(sam_ntsd, self.DA_SID, logtag=PHASE)

        ucs_dn = str(ldb_msg.dn).lower().replace(self.ucr["samba4/ldap/base"].lower(), self.ucr["ldap/base"].lower())
        uldap_msg = self.get_ucs_ldap_object(ucs_dn)
        try:
            ucs_ntsd = self.get_ntsd(uldap_msg)
        except ValueError as ex:
            utils.fail("ERROR: %s: %s" % (PHASE, ex.args[0]))
        if ucs_ntsd.as_sddl() != sam_ntsd.as_sddl():
            utils.fail("ERROR: %s: NT Security descriptor differs between %s and %s" % (PHASE, sync_from, sync_to))

        PHASE = "test"

        sam_ntsd.owner_sid = self.DU_SID
        self.admin_samdb_sdutil.modify_sd_on_dn(str(ldb_msg.dn), sam_ntsd)

        ldb_msg = self.get_ldb_gpo(self.gponame)
        sam_ntsd = self.get_ntsd(ldb_msg)
        self.assert_owner(sam_ntsd, self.DU_SID, logtag=PHASE)

        self.wait_for_s4connector_sync_to_ucs(ldb_msg, logtag=PHASE)

        uldap_msg = self.get_ucs_ldap_object(ucs_dn)
        try:
            ucs_ntsd = self.get_ntsd(uldap_msg)
        except ValueError as ex:
            utils.fail("ERROR: %s: %s" % (PHASE, ex.args[0]))

        if ucs_ntsd.as_sddl() != sam_ntsd.as_sddl():
            print('ucs_ntsd.as_sddl: %s' % ucs_ntsd.as_sddl())
            print('sam_ntsd.as_sddl: %s' % sam_ntsd.as_sddl())
            utils.fail("ERROR: %s: NT Security descriptor not synchronized from %s to %s" % (PHASE, sync_from, sync_to))

        PHASE = "cleanup"

        sam_ntsd.owner_sid = self.DA_SID
        self.admin_samdb_sdutil.modify_sd_on_dn(str(ldb_msg.dn), sam_ntsd)

        ldb_msg = self.get_ldb_gpo(self.gponame)
        sam_ntsd = self.get_ntsd(ldb_msg)
        self.assert_owner(sam_ntsd, self.DA_SID, logtag=PHASE)

        self.wait_for_s4connector_sync_to_ucs(ldb_msg, logtag=PHASE)
        uldap_msg = self.get_ucs_ldap_object(ucs_dn)
        try:
            ucs_ntsd = self.get_ntsd(uldap_msg)
        except ValueError as ex:
            utils.fail("ERROR: %s: %s" % (PHASE, ex.args[0]))

        if ucs_ntsd.as_sddl() != sam_ntsd.as_sddl():
            utils.fail("ERROR: %s: NT Security descriptor not re-synchronized from %s to %s" % (PHASE, sync_from, sync_to))


if __name__ == "__main__":
    s4connector.exit_if_connector_not_running()

    with udm_test.UCSTestUDM() as udm:
        with Testcase_GPO_Security_Descriptor_SAM_to_UDM(udm) as test:
            test.run()

        with Testcase_GPO_Security_Descriptor_UDM_to_SAM(udm) as test:
            test.run()
