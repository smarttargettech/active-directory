#!/usr/bin/python3
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# SPDX-FileCopyrightText: 2024-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import json

from univention.config_registry import ucr
from univention.udm import UDM
from univention.udm.exceptions import CreateError


MAPPED_UDM_PROPERTIES = [
    "title",
    "description",
    "displayName",
    "e-mail",
    "employeeType",
    "organisation",
    "phone",
    "uidNumber",
    "gidNumber",
    "pwdChangeNextLogin",
]  # keep in sync with MAPPED_UDM_PROPERTIES in [ucsschool-repo/4.4|5.0]/ucs-test-ucsschool/modules/...
# .../univention/testing/ucsschool/conftest.py and [ucsschool-repo/feature-kelvin]kelvin-api/tests/..
# .../conftest.py
# if changed: check kelvin-api/tests/test_route_user.test_search_filter_udm_properties()


def setup_kelvin_traeger():
    with open('/var/lib/ucs-school-import/configs/kelvin.json', 'r+') as fp:
        config = json.load(fp)
        config['configuration_checks'] = ['defaults', 'class_overwrites', 'mapped_udm_properties']
        config['mapped_udm_properties'] = MAPPED_UDM_PROPERTIES
        fp.seek(0)
        json.dump(config, fp, indent=4, sort_keys=True)


def create_extended_attr():
    sea_mod = UDM.admin().version(1).get('settings/extended_attribute')
    ldap_base = ucr['ldap/base']
    ucsschool_id_connector_last_update = sea_mod.new(superordinate=f'cn=univention,{ldap_base}')
    ucsschool_id_connector_last_update.position = f'cn=custom attributes,cn=univention,{ldap_base}'
    props = {
        'name': 'ucsschool_id_connector_last_update',
        'CLIName': 'ucsschool_id_connector_last_update',
        'shortDescription': 'Date of last update by the UCS@school ID Connector app.',
        'module': 'users/user',
        'tabName': 'UCS@school',
        'tabPosition': '9',
        'groupName': 'ID Sync',
        'groupPosition': '2',
        'translationGroupName': [('de_DE', 'ID Sync')],
        'syntax': 'string',
        'default': '',
        'multivalue': '0',
        'valueRequired': '0',
        'mayChange': '1',
        'doNotSearch': '1',
        'objectClass': 'univentionFreeAttributes',
        'ldapMapping': 'univentionFreeAttribute14',
        'deleteObjectClass': '0',
        'overwriteTab': '0',
        'fullWidth': '1',
        'disableUDMWeb': '0',
    }
    for key, value in props.items():
        setattr(ucsschool_id_connector_last_update.props, key, value)

    ucsschool_id_connector_last_update.options.extend(('ucsschoolStudent', 'ucsschoolTeacher', 'ucsschoolStaff', 'ucsschoolAdministrator'))
    try:
        ucsschool_id_connector_last_update.save()
    except CreateError:
        print('Extended attr: "ucsschool_id_connector_last_update" already exists. Ignoring.')

    ucsschool_id_connector_pw = sea_mod.new(superordinate=f'cn=univention,{ldap_base}')
    ucsschool_id_connector_pw.position = f'cn=custom attributes,cn=univention,{ldap_base}'
    props = {
        'name': 'ucsschool_id_connector_pw',
        'CLIName': 'ucsschool_id_connector_pw',
        'shortDescription': 'UCS@school ID Connector password sync.',
        'module': 'users/user',
        'syntax': 'string',
        'default': '',
        'multivalue': '0',
        'valueRequired': '0',
        'mayChange': '1',
        'doNotSearch': '1',
        'objectClass': 'univentionFreeAttributes',
        'ldapMapping': 'univentionFreeAttribute15',
        'deleteObjectClass': '0',
        'overwriteTab': '0',
        'fullWidth': '1',
        'disableUDMWeb': '1',
    }
    for key, value in props.items():
        setattr(ucsschool_id_connector_pw.props, key, value)

    ucsschool_id_connector_pw.options.extend(('ucsschoolStudent', 'ucsschoolTeacher', 'ucsschoolStaff', 'ucsschoolAdministrator'))
    try:
        ucsschool_id_connector_pw.save()
    except CreateError:
        print('Extended attr: "ucsschool_id_connector_pw" already exists. Ignoring.')
