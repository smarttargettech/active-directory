#!/usr/share/ucs-test/runner pytest-3 -s -l -vvv
## desc: Call univention-server-join on preexisting computer account with multiple macs
## bugs: [47338]
## roles: [domaincontroller_master]
## packages:
##  - univention-join
## exposure: dangerous

import subprocess

import pytest

import univention.testing.strings as uts
from univention.testing import utils


def test_join_preexisting_acc_with_multiple_macs(udm):
    memberserver1 = {
        "name": uts.random_string(),
        "mac": (uts.random_mac(), uts.random_mac()),
        "ip": "127.0.0.121",
    }
    memberserver2 = {
        "name": uts.random_string(),
        "mac": memberserver1["mac"],
        "ip": "127.0.0.122",
    }
    memberserver1["dn"] = udm.create_object("computers/memberserver", set=memberserver1)
    utils.verify_ldap_object(memberserver1["dn"], expected_attr={"macAddress": memberserver1["mac"]})
    join_member_with_preexisting_acc(memberserver1, udm)
    join_member_with_conflicting_mac(memberserver2)


def join_member_with_preexisting_acc(memberserver, udm):
    print(memberserver)
    for mac in memberserver["mac"]:
        # This removes all but one mac
        subprocess.check_call([
            "/usr/share/univention-join/univention-server-join",
            "-role", "memberserver",
            "-hostname", memberserver["name"],
            "-ip", memberserver["ip"],
            "-mac", mac,
        ])
        # Re-add macs
        udm.modify_object("computers/memberserver", dn=memberserver["dn"], mac=memberserver["mac"])
        utils.verify_ldap_object(memberserver["dn"], expected_attr={"macAddress": memberserver["mac"]})


def join_member_with_conflicting_mac(memberserver):
    print(memberserver)
    for mac in memberserver["mac"]:
        with pytest.raises(subprocess.CalledProcessError) as exc:
            # This should fail because the macs conflict between memberserver1 and memberserver2
            print(subprocess.check_output([
                "/usr/share/univention-join/univention-server-join",
                "-role", "memberserver",
                "-hostname", memberserver["name"],
                "-ip", memberserver["ip"],
                "-mac", mac,
            ]))

        expected_error = f"E: failed to create Managed Node (1) [E: Object exists: (mac) The MAC address is already in use: {mac}.]"
        error_message = exc.value.output.decode('UTF-8')
        assert expected_error in error_message
