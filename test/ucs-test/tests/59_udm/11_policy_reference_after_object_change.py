#!/usr/share/ucs-test/runner pytest-3 -s -l -vv
## desc: policy reference works after changing the objects dn
## tags: [udm,apptest]
## roles: [domaincontroller_master]
## bugs: [41694]
## exposure: dangerous
## packages:
##   - univention-config
##   - univention-directory-manager-tools

import pytest

from univention.testing import utils
from univention.testing.strings import random_string


@pytest.mark.tags('udm', 'apptest')
@pytest.mark.roles('domaincontroller_master')
@pytest.mark.exposure('dangerous')
@pytest.mark.parametrize('object_type', ['container/cn', 'mail/domain'])
def test_policy_reference_after_object_change(udm, object_type):
    """Policy reference works after changing the objects dn"""
    # bugs: [41694]
    print('testing', object_type)
    policy = udm.create_object('policies/pwhistory', **{'name': random_string()})  # noqa: PIE804
    old_dn = udm.create_object(object_type, **{'name': random_string()})  # noqa: PIE804

    new_dn = udm.modify_object(object_type, **{'name': random_string(), 'dn': old_dn, 'policy_reference': policy})  # noqa: PIE804
    print('new_dn', new_dn)
    utils.verify_ldap_object(new_dn, {'univentionPolicyReference': [policy]})
    print('old_dn', old_dn)
    utils.verify_ldap_object(old_dn, should_exist=False)
