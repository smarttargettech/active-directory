#!/usr/share/ucs-test/runner pytest-3 -s -l -vv
## desc: Create UDM object with multi-malued RDN
## roles: [domaincontroller_master,domaincontroller_backup,domaincontroller_slave,memberserver]
## exposure: careful
## bugs: [40129]

import pytest
from ldap import AVA_STRING
from ldap.dn import dn2str, str2dn

from univention.testing.strings import random_name
from univention.testing.utils import verify_ldap_object, wait_for_replication


MODULE = 'tests/ipservice'


@pytest.mark.tags('udm')
@pytest.mark.roles('domaincontroller_master', 'domaincontroller_backup', 'domaincontroller_slave', 'memberserver')
@pytest.mark.exposure('careful')
def test_multi_valued_rdn(udm):
    """Create UDM object with multi-malued RDN"""
    # bugs: [40129]
    print("Creating...")
    testing = udm.create_object('container/cn', name=random_name())
    str_tcp = udm.create_object(MODULE, position=testing, name='echo', protocol='tcp', port='7')
    str_udp = udm.create_object(MODULE, position=testing, name='echo', protocol='udp', port='7')
    wait_for_replication()

    print("Testing DNs...")
    verify_ldap_object(str_tcp)
    verify_ldap_object(str_udp)

    print("Testing reversed DNs...")
    dn_tcp = str2dn(str_tcp)
    dn_tcp[0].reverse()
    verify_ldap_object(dn2str(dn_tcp))

    dn_udp = str2dn(str_udp)
    dn_udp[0].reverse()
    verify_ldap_object(dn2str(dn_udp))

    print("Testing modify...")
    DESC = 'The UDP echo service'
    str_udp = udm.modify_object(MODULE, dn=str_udp, description=DESC)
    verify_ldap_object(str_udp, expected_attr={'description': [DESC]}, strict=False)

    print("Testing delete...")
    udm.remove_object(MODULE, dn=str_udp)
    verify_ldap_object(str_udp, should_exist=False)

    print("Testing rename...")
    new_tcp = udm.modify_object(MODULE, dn=str_tcp, port='8')
    # Bug #41694: does NOT return new_dn !
    ATTR = 'ipServicePort'
    new_tcp = dn2str([
        [
                    (ATTR, '8', AVA_STRING) if ava[0] == ATTR else ava
            for ava in rdn
        ] for rdn in dn_tcp
    ])

    verify_ldap_object(str_tcp, should_exist=False)
    verify_ldap_object(new_tcp)
