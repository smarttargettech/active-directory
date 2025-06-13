#!/usr/bin/python3
#
# Univention AD Connector
#  this file defines the mapping between AD and UCS
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2004-2025 Univention GmbH
#
# https://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <https://www.gnu.org/licenses/>.


import importlib.util

import univention.connector.ad
import univention.connector.ad.password
from univention.config_registry import ConfigRegistry
from univention.connector.ad import proxyAddresses


configRegistry = ConfigRegistry()
configRegistry.load()


def ignore_filter_from_tmpl(template, ucr_key, default=''):
    """
    Construct an `ignore_filter` from a `ucr_key`
    (`connector/ad/mapping/*/ignorelist`, a comma delimited list of values), as
    specified by `template` while correctly escaping the filter-expression.

    `template` must be formatted as required by `format_escaped`.

    >>> ignore_filter_from_tmpl('(cn={0!e})',
    ... 'connector/ad/mapping/nonexistend/ignorelist',
    ... 'one,two,three')
    '(|(cn=one)(cn=two)(cn=three))'
    """
    from univention.connector.ad import format_escaped
    variables = [v for v in configRegistry.get(ucr_key, default).split(',') if v]
    filter_parts = [format_escaped(template, v) for v in variables]
    if filter_parts:
        return '(|{})'.format(''.join(filter_parts))
    return ''


def ignore_filter_from_attr(attribute, ucr_key, default=''):
    """
    Convenience-wrapper around `ignore_filter_from_tmpl()`.

    This expects a single `attribute` instead of a `template` argument.

    >>> ignore_filter_from_attr('cn',
    ... 'connector/ad/mapping/nonexistend/ignorelist',
    ... 'one,two,three')
    '(|(cn=one)(cn=two)(cn=three))'
    """
    template = f'({attribute}={{0!e}})'
    return ignore_filter_from_tmpl(template, ucr_key, default)


def get_mapping(configbasename='connector'):
    ad_mapping = create_mapping(configbasename)
    return load_localmapping(ad_mapping, '/etc/univention/%s/ad/localmapping.py' % configbasename)


def create_mapping(configbasename='connector'):
    def connector(string):
        return string % (configbasename,)

    global_allow_subtree_ad = []
    global_allow_subtree_ucs = []

    for key in configRegistry:
        if key.startswith(connector('%s/ad/mapping/allowsubtree')):
            if key.endswith('/ad'):
                global_allow_subtree_ad.append(configRegistry[key])
            elif key.endswith('/ucs'):
                global_allow_subtree_ucs.append(configRegistry[key])

    global_ignore_subtree = [
        'cn=univention,%(ldap/base)s' % configRegistry,
        'cn=policies,%(ldap/base)s' % configRegistry,
        'cn=shares,%(ldap/base)s' % configRegistry,
        'cn=printers,%(ldap/base)s' % configRegistry,
        'cn=networks,%(ldap/base)s' % configRegistry,
        'cn=kerberos,%(ldap/base)s' % configRegistry,
        'cn=dhcp,%(ldap/base)s' % configRegistry,
        'cn=dns,%(ldap/base)s' % configRegistry,
        'cn=mail,%(ldap/base)s' % configRegistry,
        'cn=samba,%(ldap/base)s' % configRegistry,
        'cn=nagios,%(ldap/base)s' % configRegistry,
        connector('cn=System,%%(%s/ad/ldap/base)s') % configRegistry,
        connector('ou=Grp Policy Users,%%(%s/ad/ldap/base)s') % configRegistry,
        connector('cn=Builtin,%%(%s/ad/ldap/base)s') % configRegistry,
        connector('cn=ForeignSecurityPrincipals,%%(%s/ad/ldap/base)s') % configRegistry,
        connector('ou=Domain Controllers,%%(%s/ad/ldap/base)s') % configRegistry,
        connector('cn=Program Data,%%(%s/ad/ldap/base)s') % configRegistry,
        connector('cn=Configuration,%%(%s/ad/ldap/base)s') % configRegistry,
        'cn=opsi,%(ldap/base)s' % configRegistry,
        connector('cn=Microsoft Exchange System Objects,%%(%s/ad/ldap/base)s') % configRegistry,
    ]

    for key in configRegistry:
        if key.startswith(connector('%s/ad/mapping/ignoresubtree/')):
            global_ignore_subtree.append(configRegistry[key])

    user_ignore_list = ignore_filter_from_tmpl('(uid={0!e})(CN={0!e})', connector('%s/ad/mapping/user/ignorelist'))
    user_ignore_filter = configRegistry.get(connector('%s/ad/mapping/user/ignorefilter'), '')
    if user_ignore_filter and not user_ignore_filter.startswith('('):
        user_ignore_filter = f'({user_ignore_filter})'
    user_ignore_filter = '(|{}{}{})'.format('(userAccountControl=2080)', user_ignore_filter, user_ignore_list)

    ignore_filter_parts = '(groupType=-2147483643)(groupType=4)(univentionGroupType=-2147483643)(univentionGroupType=4)'
    group_ignore_filter = configRegistry.get(connector('%s/ad/mapping/group/ignorefilter'), '')
    if group_ignore_filter and not group_ignore_filter.startswith('('):
        group_ignore_filter = f'({group_ignore_filter})'
    if configRegistry.is_false(connector('%s/ad/mapping/group/grouptype'), False):
        ignore_filter_parts += '(sambaGroupType=5)(groupType=5)'
    ignore_filter_parts += ignore_filter_from_attr('cn', connector('%s/ad/mapping/group/ignorelist'))
    group_ignore_filter = f'(|{group_ignore_filter}{ignore_filter_parts})'

    computer_ignore_filter = configRegistry.get(connector('%s/ad/mapping/windowscomputer/ignorefilter'), '')
    if computer_ignore_filter and not computer_ignore_filter.startswith('('):
        computer_ignore_filter = f'({computer_ignore_filter})'
    computer_ignore_parts = ignore_filter_from_attr('cn', connector('%s/ad/mapping/windowscomputer/ignorelist'))
    computer_ignore_filter = f'(|{computer_ignore_filter}{computer_ignore_parts})' if computer_ignore_filter or computer_ignore_parts else ''

    container_ignore_attrs = ignore_filter_from_attr('cn', connector('%s/ad/mapping/container/ignorelist'), 'mail,kerberos')
    container_ignore_filter = configRegistry.get(connector('%s/ad/mapping/container/ignorefilter'), '')
    if container_ignore_filter and not container_ignore_filter.startswith('('):
        container_ignore_filter = f'({container_ignore_filter})'
    container_ignore_filter = f'(|{container_ignore_filter}{container_ignore_attrs})' if container_ignore_filter or container_ignore_attrs else ''

    ou_ignore_attrs = ignore_filter_from_attr('ou', connector('%s/ad/mapping/ou/ignorelist'))
    ou_ignore_filter = configRegistry.get(connector('%s/ad/mapping/ou/ignorefilter'), '')
    if ou_ignore_filter and not ou_ignore_filter.startswith('('):
        ou_ignore_filter = f'({ou_ignore_filter})'
    ou_ignore_filter = f'(|{ou_ignore_filter}{ou_ignore_attrs})' if ou_ignore_filter or ou_ignore_attrs else ''

    ad_mapping = {
        'user': univention.connector.property(
            ucs_default_dn='cn=users,%(ldap/base)s' % configRegistry,
            con_default_dn=connector('cn=users,%%(%s/ad/ldap/base)s') % configRegistry,
            ucs_module='users/user',
            # read, write, sync, none
            sync_mode=configRegistry.get(connector('%s/ad/mapping/user/syncmode'), configRegistry.get(connector('%s/ad/mapping/syncmode'))),
            scope='sub',
            con_search_filter='(&(objectClass=user)(!objectClass=computer))',
            match_filter='(|(&(objectClass=posixAccount)(objectClass=sambaSamAccount))(objectClass=user))',
            allow_subtree=global_allow_subtree_ucs + global_allow_subtree_ad,
            ignore_filter=user_ignore_filter or None,
            ignore_subtree=global_ignore_subtree,
            con_create_objectclass=['top', 'user', 'person', 'organizationalPerson'],
            dn_mapping_function=[univention.connector.ad.user_dn_mapping],
            attributes={  # from UCS Module
                'samAccountName': univention.connector.attribute(
                    ucs_attribute='username',
                    ldap_attribute='uid',
                    con_attribute='sAMAccountName',
                    required=1,
                    compare_function=univention.connector.compare_lowercase,
                ),
                'givenName': univention.connector.attribute(
                    ucs_attribute='firstname',
                    ldap_attribute='givenName',
                    con_attribute='givenName',
                ),
                'sn': univention.connector.attribute(
                    ucs_attribute='lastname',
                    ldap_attribute='sn',
                    con_attribute='sn',
                ),
            },
            ucs_create_functions=[
                univention.connector.set_ucs_passwd_user,
                univention.connector.check_ucs_lastname_user,
                univention.connector.set_primary_group_user,
            ],
            post_con_modify_functions=list(filter(None, [
                univention.connector.ad.set_userPrincipalName_from_ucr,
                univention.connector.ad.password.password_sync_ucs if configRegistry.is_false(connector('%s/ad/mapping/user/password/disabled'), True) else None,
                univention.connector.ad.primary_group_sync_from_ucs,
                univention.connector.ad.object_memberships_sync_from_ucs,
                univention.connector.ad.disable_user_from_ucs,
            ])),
            post_ucs_modify_functions=list(filter(None, [
                univention.connector.ad.password.password_sync_kinit if configRegistry.is_false(connector('%s/ad/mapping/user/password/disabled'), True) and configRegistry.is_true(connector('%s/ad/mapping/user/password/kinit'), False) else None,
                univention.connector.ad.password.password_sync if configRegistry.is_false(connector('%s/ad/mapping/user/password/disabled'), True) and not configRegistry.is_true(connector('%s/ad/mapping/user/password/kinit'), False) else None,
                univention.connector.ad.set_univentionObjectFlag_to_synced,
                univention.connector.ad.primary_group_sync_to_ucs,
                univention.connector.ad.object_memberships_sync_to_ucs,
                univention.connector.ad.disable_user_to_ucs,
            ])),
            post_attributes={
                'organisation': univention.connector.attribute(
                    ucs_attribute='organisation',
                    ldap_attribute='o',
                    con_attribute=configRegistry.get(connector('%s/ad/mapping/organisation'), 'company'),
                ),
                'Exchange-Homeserver': univention.connector.attribute(
                    ucs_attribute='Exchange-Homeserver',
                    ldap_attribute='univentionADmsExchHomeServerName',
                    con_attribute='msExchHomeServerName',
                ),
                'Exchange-homeMDB': univention.connector.attribute(
                    ucs_attribute='Exchange-homeMDB',
                    ldap_attribute='univentionADhomeMDB',
                    con_attribute='homeMDB',
                ),
                'Exchange-Nickname': univention.connector.attribute(
                    ucs_attribute='Exchange-Nickname',
                    ldap_attribute='univentionADmailNickname',
                    con_attribute='mailNickname',
                ),
                'mailPrimaryAddress': univention.connector.attribute(
                    ucs_attribute='mailPrimaryAddress',
                    ldap_attribute='mailPrimaryAddress',
                    con_attribute='proxyAddresses',
                    mapping=(
                        proxyAddresses.to_proxyAddresses,
                        proxyAddresses.to_mailPrimaryAddress,
                    ),
                    compare_function=proxyAddresses.equal,
                ),
                'mailPrimaryAddress_to_mail': univention.connector.attribute(
                    sync_mode='write',
                    ucs_attribute='mailPrimaryAddress',
                    ldap_attribute='mailPrimaryAddress',
                    con_attribute='mail',
                ),
                'mailAlternativeAddress': univention.connector.attribute(
                    sync_mode='read' if configRegistry.is_true(connector('%s/ad/mapping/user/primarymail')) else 'sync',  # proxyAddresses.to_mailPrimaryAddress does the write
                    ucs_attribute='mailAlternativeAddress',
                    ldap_attribute='mailAlternativeAddress',
                    con_attribute='proxyAddresses',
                    mapping=(
                        None,
                        proxyAddresses.to_mailAlternativeAddress,
                    ),
                    compare_function=proxyAddresses.equal,
                ),
                'description': univention.connector.attribute(
                    ucs_attribute='description',
                    ldap_attribute='description',
                    con_attribute='description',
                ),
                'street': univention.connector.attribute(
                    ucs_attribute='street',
                    ldap_attribute='street',
                    con_attribute='streetAddress',
                ),
                'city': univention.connector.attribute(
                    ucs_attribute='city',
                    ldap_attribute='l',
                    con_attribute='l',
                ),
                'postcode': univention.connector.attribute(
                    ucs_attribute='postcode',
                    ldap_attribute='postalCode',
                    con_attribute='postalCode',
                ),
                'sambaWorkstations': univention.connector.attribute(
                    ucs_attribute='sambaUserWorkstations',
                    ldap_attribute='sambaUserWorkstations',
                    con_attribute='userWorkstations',
                ),
                # 'sambaLogonHours': univention.connector.attribute(
                #    ucs_attribute='sambaLogonHours',
                #    ldap_attribute='sambaLogonHours',
                #    con_attribute='logonHours',
                # ),
                'profilepath': univention.connector.attribute(
                    ucs_attribute='profilepath',
                    ldap_attribute='sambaProfilePath',
                    con_attribute='profilePath',
                ),
                'scriptpath': univention.connector.attribute(
                    ucs_attribute='scriptpath',
                    ldap_attribute='sambaLogonScript',
                    con_attribute='scriptPath',
                ),
                'telephoneNumber': univention.connector.attribute(
                    ucs_attribute='phone',
                    ldap_attribute='telephoneNumber',
                    con_attribute='telephoneNumber',
                    con_other_attribute='otherTelephone',
                ),
                'homePhone': univention.connector.attribute(
                    ucs_attribute='homeTelephoneNumber',
                    ldap_attribute='homePhone',
                    con_attribute='homePhone',
                    con_other_attribute='otherHomePhone',
                ),
                'mobilePhone': univention.connector.attribute(
                    ucs_attribute='mobileTelephoneNumber',
                    ldap_attribute='mobile',
                    con_attribute='mobile',
                    con_other_attribute='otherMobile',
                ),
                'pager': univention.connector.attribute(
                    ucs_attribute='pagerTelephoneNumber',
                    ldap_attribute='pager',
                    con_attribute='pager',
                    con_other_attribute='otherPager',
                ),
                'displayName': univention.connector.attribute(
                    ucs_attribute='displayName',
                    ldap_attribute='displayName',
                    con_attribute='displayName',
                ),
            },
        ),
        'group': univention.connector.property(
            ucs_default_dn='cn=groups,%(ldap/base)s' % configRegistry,
            con_default_dn=connector('cn=Users,%%(%s/ad/ldap/base)s') % configRegistry,
            ucs_module='groups/group',
            sync_mode=configRegistry.get(connector('%s/ad/mapping/group/syncmode'), configRegistry.get(connector('%s/ad/mapping/syncmode'))),
            scope='sub',
            allow_subtree=global_allow_subtree_ucs + global_allow_subtree_ad,
            ignore_filter=group_ignore_filter or None,
            ignore_subtree=global_ignore_subtree,
            con_search_filter='objectClass=group',
            con_create_objectclass=['top', 'group'],
            post_con_modify_functions=[
                univention.connector.ad.group_members_sync_from_ucs,
                univention.connector.ad.object_memberships_sync_from_ucs,
            ],
            post_ucs_modify_functions=[
                univention.connector.ad.set_univentionObjectFlag_to_synced,
                univention.connector.ad.group_members_sync_to_ucs,
                univention.connector.ad.object_memberships_sync_to_ucs,
            ],
            dn_mapping_function=[univention.connector.ad.group_dn_mapping],
            attributes={
                'cn': univention.connector.attribute(
                    ucs_attribute='name',
                    ldap_attribute='cn',
                    con_attribute='sAMAccountName',
                    required=True,
                    compare_function=univention.connector.compare_lowercase,
                ),
                'groupType': univention.connector.attribute(
                    ucs_attribute='adGroupType',
                    ldap_attribute='univentionGroupType',
                    con_attribute='groupType',
                ),
                'description': univention.connector.attribute(
                    ucs_attribute='description',
                    ldap_attribute='description',
                    con_attribute='description',
                ),
                'mailAddress': univention.connector.attribute(
                    sync_mode='read',
                    ucs_attribute='mailAddress',
                    ldap_attribute='mailPrimaryAddress',
                    con_attribute='proxyAddresses',
                    mapping=(
                        proxyAddresses.to_proxyAddresses,
                        proxyAddresses.to_mailPrimaryAddress,
                    ),
                    compare_function=proxyAddresses.equal,
                ),
                'mailPrimaryAddress_to_mail': univention.connector.attribute(
                    sync_mode='write',
                    ucs_attribute='mailAddress',
                    ldap_attribute='mailPrimaryAddress',
                    con_attribute='mail',
                ),
                'mailAlternativeAddress': univention.connector.attribute(
                    sync_mode='read' if configRegistry.is_true(connector('%s/ad/mapping/group/primarymail')) else 'sync',  # proxyAddresses.to_mailPrimaryAddress does the write
                    ucs_attribute='mailAlternativeAddress',
                    ldap_attribute='mailAlternativeAddress',
                    con_attribute='proxyAddresses',
                    mapping=(
                        None,
                        proxyAddresses.to_mailAlternativeAddress,
                    ),
                    compare_function=proxyAddresses.equal,
                ),
                'Exchange-Nickname': univention.connector.attribute(
                    ucs_attribute='Exchange-Nickname',
                    ldap_attribute='univentionADmailNickname',
                    con_attribute='mailNickname',
                ),
            },
            mapping_table={
                'cn': [
                    ('Domain Users', 'Domänen-Benutzer'),
                    ('Domain Admins', 'Domänen-Admins'),
                    ('Windows Hosts', 'Domänencomputer'),
                    ('Domain Guests', 'Domänen-Gäste'),
                ],
            },
        ),
        'windowscomputer': univention.connector.property(
            ucs_default_dn='cn=computers,%(ldap/base)s' % configRegistry,
            con_default_dn=connector('cn=computers,%%(%s/ad/ldap/base)s') % configRegistry,
            ucs_module='computers/windows',
            ucs_module_others=['computers/memberserver', 'computers/linux', 'computers/ubuntu', 'computers/macos'],
            sync_mode=configRegistry.get(connector('%s/ad/mapping/computer/syncmode'), configRegistry.get(connector('%s/ad/mapping/syncmode'))),
            post_ucs_modify_functions=[
                univention.connector.ad.set_univentionObjectFlag_to_synced,
            ],
            scope='sub',
            dn_mapping_function=[univention.connector.ad.windowscomputer_dn_mapping],
            con_search_filter='(&(objectClass=computer)(userAccountControl:1.2.840.113556.1.4.803:=4096))',
            # ignore_filter='userAccountControl=4096',
            match_filter='(|(&(objectClass=univentionWindows)(!(univentionServerRole=windows_domaincontroller)))(objectClass=computer)(objectClass=univentionMemberServer)(objectClass=univentionUbuntuClient)(objectClass=univentionLinuxClient)(objectClass=univentionMacOSClient))',
            allow_subtree=global_allow_subtree_ucs + global_allow_subtree_ad,
            ignore_subtree=global_ignore_subtree,
            ignore_filter=computer_ignore_filter or None,
            con_create_objectclass=['top', 'computer'],
            con_create_attributes=[('userAccountControl', [b'4096'])],
            attributes={
                'cn': univention.connector.attribute(
                    ucs_attribute='name',
                    ldap_attribute='cn',
                    con_attribute='cn',
                    required=True,
                    compare_function=univention.connector.compare_lowercase,
                ),
                'samAccountName': univention.connector.attribute(
                    ldap_attribute='uid',
                    con_attribute='sAMAccountName',
                    compare_function=univention.connector.compare_lowercase,
                    sync_mode='write',
                ),
                'description': univention.connector.attribute(
                    ucs_attribute='description',
                    ldap_attribute='description',
                    con_attribute='description',
                ),
                'operatingSystem': univention.connector.attribute(
                    ucs_attribute='operatingSystem',
                    ldap_attribute='univentionOperatingSystem',
                    con_attribute='operatingSystem',
                ),
                'operatingSystemVersion': univention.connector.attribute(
                    ucs_attribute='operatingSystemVersion',
                    ldap_attribute='univentionOperatingSystemVersion',
                    con_attribute='operatingSystemVersion',
                ),
            },
        ),
        'container': univention.connector.property(
            ucs_module='container/cn',
            sync_mode=configRegistry.get(connector('%s/ad/mapping/container/syncmode'), configRegistry.get(connector('%s/ad/mapping/syncmode'))),
            scope='sub',
            con_search_filter='(|(objectClass=container)(objectClass=builtinDomain))',  # builtinDomain is cn=builtin (with group cn=Administrators)
            allow_subtree=global_allow_subtree_ucs + global_allow_subtree_ad,
            ignore_filter=container_ignore_filter or None,
            ignore_subtree=global_ignore_subtree,
            post_ucs_modify_functions=[
                univention.connector.ad.set_univentionObjectFlag_to_synced,
            ],
            con_create_objectclass=['top', 'container'],
            attributes={
                'cn': univention.connector.attribute(
                    ucs_attribute='name',
                    ldap_attribute='cn',
                    con_attribute='cn',
                    required=1,
                    compare_function=univention.connector.compare_lowercase,
                ),
                'description': univention.connector.attribute(
                    ucs_attribute='description',
                    ldap_attribute='description',
                    con_attribute='description',
                ),
            },
        ),
        'ou': univention.connector.property(
            ucs_module='container/ou',
            sync_mode=configRegistry.get(connector('%s/ad/mapping/ou/syncmode'), configRegistry.get(connector('%s/ad/mapping/syncmode'))),
            scope='sub',
            con_search_filter='objectClass=organizationalUnit',
            allow_subtree=global_allow_subtree_ucs + global_allow_subtree_ad,
            ignore_filter=ou_ignore_filter or None,
            ignore_subtree=global_ignore_subtree,
            post_ucs_modify_functions=[
                univention.connector.ad.set_univentionObjectFlag_to_synced,
            ],
            con_create_objectclass=['top', 'organizationalUnit'],
            attributes={
                'ou': univention.connector.attribute(
                    ucs_attribute='name',
                    ldap_attribute='ou',
                    con_attribute='ou',
                    required=True,
                    compare_function=univention.connector.compare_lowercase,
                ),
                'description': univention.connector.attribute(
                    ucs_attribute='description',
                    ldap_attribute='description',
                    con_attribute='description',
                ),
            },
        ),
    }

    # allow filter
    for obj_type in ad_mapping.keys():  # noqa: PLC0206
        allow_filter = configRegistry.get(connector(f'%s/ad/mapping/{obj_type}/allowfilter'), '')
        if allow_filter:
            if not allow_filter.startswith('('):
                allow_filter = f'({allow_filter})'
            ad_mapping[obj_type].allow_filter = allow_filter

    # users
    if configRegistry.is_false(connector('%s/ad/mapping/user/exchange'), True):
        ad_mapping['user'].post_attributes.pop('Exchange-Homeserver')
        ad_mapping['user'].post_attributes.pop('Exchange-homeMDB')
        ad_mapping['user'].post_attributes.pop('Exchange-Nickname')
    if not configRegistry.is_true(connector('%s/ad/mapping/user/primarymail')):
        ad_mapping['user'].post_attributes.pop('mailPrimaryAddress')
        ad_mapping['user'].post_attributes.pop('mailPrimaryAddress_to_mail')
    if not configRegistry.is_true(connector('%s/ad/mapping/user/alternativemail')):
        ad_mapping['user'].post_attributes.pop('mailAlternativeAddress')

    # groups
    if not configRegistry.is_true(connector('%s/ad/mapping/group/grouptype'), True):
        ad_mapping['group'].attributes.pop('groupType')
    if not configRegistry.is_true(connector('%s/ad/mapping/group/primarymail')):
        ad_mapping['group'].attributes.pop('mailAddress')
        ad_mapping['group'].attributes.pop('mailPrimaryAddress_to_mail')
    if not configRegistry.is_true(connector('%s/ad/mapping/group/alternativemail')):
        ad_mapping['group'].attributes.pop('mailAlternativeAddress')
    if configRegistry.is_false(connector('%s/ad/mapping/group/exchange'), True):
        ad_mapping['group'].attributes.pop('Exchange-Nickname')
    if configRegistry.get(connector('%s/ad/mapping/group/language')) not in ['de', 'DE']:
        ad_mapping['group'].mapping_table.pop('cn')

    return ad_mapping


def load_localmapping(ad_mapping, filename='/etc/univention/connector/ad/localmapping.py'):
    try:
        spec = importlib.util.spec_from_file_location('localmapping', filename)
        mapping = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mapping)
        mapping_hook = mapping.mapping_hook
    except (OSError, AttributeError):
        return ad_mapping
    else:
        return mapping_hook(ad_mapping)
