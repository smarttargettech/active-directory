#!/usr/share/ucs-test/runner pytest-3
## desc: Create a valid ldap schema object
## tags: [udm,udm-settings,udm-ldapextensions,apptest]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - univention-directory-manager-tools

import base64
import bz2
import os
import shlex
import shutil
import subprocess

import ldap.dn
import pytest

import univention.admin.modules as udm_modules
import univention.testing.strings as uts
import univention.testing.udm as udm_test
from univention.admin import uldap
from univention.testing import strings, utils


class Test_LDAPSchema:
    """Test udm settings/ldapschema"""

    @pytest.mark.tags('udm-ldapextensions', 'apptest')
    @pytest.mark.roles('domaincontroller_master')
    @pytest.mark.exposure('dangerous')
    def test_create_ldap_schema(self, udm):
        """Create a valid ldap schema object"""
        schema_name = uts.random_name()
        filename = '90%s' % uts.random_name()
        data = '# schema test'
        schema = udm.create_object('settings/ldapschema', position=udm.UNIVENTION_CONTAINER, name=schema_name, filename=filename, data=(base64.b64encode(bz2.compress(data.encode('UTF-8')))).decode('ASCII'))
        utils.verify_ldap_object(schema, {'cn': [schema_name]})

        udm.remove_object('settings/ldapschema', dn=schema)
        with pytest.raises(utils.LDAPObjectNotFound):
            utils.verify_ldap_object(schema, {'cn': [schema_name]}, retry_count=1)

    @pytest.mark.tags('udm-ldapextensions', 'apptest')
    @pytest.mark.roles('domaincontroller_master')
    @pytest.mark.exposure('dangerous')
    @pytest.mark.parametrize('active', ['TRUE', 'FALSE'])
    def test_create_full_ldap_schema(self, udm, active):
        """Create a full ldap schema objects"""
        schema_name = uts.random_name()
        filename = '90%s' % uts.random_name()
        data = '# schema test'
        package_version = '99.%s-%s' % (uts.random_int(), uts.random_int())
        package = uts.random_name()
        appidentifier = '%s' % uts.random_name()

        schema = udm.create_object(
            'settings/ldapschema',
            position=udm.UNIVENTION_CONTAINER,
            name=schema_name,
            data=base64.b64encode(bz2.compress(data.encode('UTF-8'))).decode('ASCII'),
            filename=filename,
            packageversion=package_version,
            appidentifier=appidentifier,
            package=[package],
            active=active)

        utils.verify_ldap_object(schema, {
            'cn': [schema_name],
            'univentionLDAPSchemaData': [bz2.compress(data.encode('UTF-8'))],
            'univentionLDAPSchemaFilename': [filename],
            'univentionOwnedByPackage': [package],
            'univentionOwnedByPackageVersion': [package_version],
            'univentionAppIdentifier': [appidentifier],
            'univentionLDAPSchemaActive': [active],
            'univentionObjectType': ['settings/ldapschema'],
        })


class Test_LDAPACL:
    """Test udm settings/ldapacl"""

    @pytest.mark.tags('udm-ldapextensions', 'apptest')
    @pytest.mark.roles('domaincontroller_master')
    @pytest.mark.exposure('dangerous')
    def test_create_invalid_ldap_schema(self, udm):
        """Try to create invalid ldap schema objects"""
        schema_name = uts.random_name()
        filename = '/90%s' % uts.random_name()
        data = '# schema test'
        with pytest.raises(udm_test.UCSTestUDM_CreateUDMObjectFailed):
            udm.create_object('settings/ldapschema', name=schema_name, filename=filename, data=base64.b64encode(bz2.compress(data.encode('UTF-8'))).decode('ASCII'))

        schema_name = uts.random_name()
        filename = '90%s' % uts.random_name()
        data = '# schema test'
        with pytest.raises(udm_test.UCSTestUDM_CreateUDMObjectFailed):
            udm.create_object('settings/ldapschema', name=schema_name, filename=filename, data=base64.b64encode(data.encode('UTF-8')).decode('ASCII'))

        schema_name = uts.random_name()
        filename = '90%s' % uts.random_name()
        data = '# schema test'
        with pytest.raises(udm_test.UCSTestUDM_CreateUDMObjectFailed):
            udm.create_object('settings/ldapschema', name=schema_name, filename=filename, data=base64.b64encode(bz2.compress(data.encode('UTF-8'))).decode('ASCII'), active='YES')

    @pytest.mark.tags('udm-ldapextensions', 'apptest')
    @pytest.mark.roles('domaincontroller_master')
    @pytest.mark.exposure('dangerous')
    def test_create_ldap_acl(self, udm):
        """Create a valid ldap acl object"""
        acl_name = uts.random_name()
        filename = '90%s' % uts.random_name()
        data = '# access to  *'
        acl = udm.create_object('settings/ldapacl', position=udm.UNIVENTION_CONTAINER, name=acl_name, filename=filename, data=base64.b64encode(bz2.compress(data.encode('UTF-8'))).decode('ASCII'))
        utils.verify_ldap_object(acl, {'cn': [acl_name]})

        udm.remove_object('settings/ldapacl', dn=acl)
        with pytest.raises(utils.LDAPObjectNotFound):
            utils.verify_ldap_object(acl, {'cn': [acl_name]}, retry_count=1)

    @pytest.mark.tags('udm-ldapextensions', 'apptest')
    @pytest.mark.roles('domaincontroller_master')
    @pytest.mark.exposure('dangerous')
    @pytest.mark.parametrize('active', ['TRUE', 'FALSE'])
    def test_create_full_ldap_acl(self, udm, active):
        """Create a full ldap acl objects"""
        acl_name = uts.random_name()
        filename = '90%s' % uts.random_name()
        data = '# acl test'
        package_version = '99.%s-%s' % (uts.random_int(), uts.random_int())
        package = uts.random_name()
        appidentifier = '%s' % uts.random_name()
        ucsversionstart = '1.2-0'
        ucsversionend = '1.3-99'

        acl = udm.create_object(
            'settings/ldapacl',
            position=udm.UNIVENTION_CONTAINER,
            name=acl_name,
            data=base64.b64encode(bz2.compress(data.encode('UTF-8'))).decode('ASCII'),
            filename=filename,
            package=package,
            packageversion=package_version,
            appidentifier=appidentifier,
            ucsversionstart=ucsversionstart,
            ucsversionend=ucsversionend,
            active=active)

        utils.verify_ldap_object(acl, {
            'cn': [acl_name],
            'univentionLDAPACLData': [bz2.compress(data.encode('UTF-8'))],
            'univentionLDAPACLFilename': [filename],
            'univentionOwnedByPackage': [package],
            'univentionOwnedByPackageVersion': [package_version],
            'univentionAppIdentifier': [appidentifier],
            'univentionUCSVersionStart': [ucsversionstart],
            'univentionUCSVersionEnd': [ucsversionend],
            'univentionLDAPACLActive': [active],
            'univentionObjectType': ['settings/ldapacl'],
        })

    @pytest.mark.tags('udm-ldapextensions', 'apptest')
    @pytest.mark.roles('domaincontroller_master')
    @pytest.mark.exposure('dangerous')
    def test_create_invalid_ldap_acl(self, udm):
        """Try to create invalid ldap acl objects"""
        acl_name = uts.random_name()
        filename = '/90%s' % uts.random_name()
        data = '# acl test'
        with pytest.raises(udm_test.UCSTestUDM_CreateUDMObjectFailed):
            udm.create_object('settings/ldapacl', name=acl_name, filename=filename, data=base64.b64encode(bz2.compress(data.encode('UTF-8'))).decode('ASCII'))

        acl_name = uts.random_name()
        filename = '90%s' % uts.random_name()
        data = '# acl test'
        with pytest.raises(udm_test.UCSTestUDM_CreateUDMObjectFailed):
            udm.create_object('settings/ldapacl', name=acl_name, filename=filename, data=base64.b64encode(data.encode('UTF-8')).decode('ASCII'))

        acl_name = uts.random_name()
        filename = '90%s' % uts.random_name()
        data = '# acl test'
        with pytest.raises(udm_test.UCSTestUDM_CreateUDMObjectFailed):
            udm.create_object('settings/ldapacl', name=acl_name, filename=filename, data=base64.b64encode(bz2.compress(data.encode('UTF-8'))).decode('ASCII'), active='YES')


# TODO: add a test case for subdirectories
@pytest.mark.parametrize('modify', [False, True])
@pytest.mark.parametrize('prefix', ['/', '../../../../../../../../../'])
@pytest.mark.parametrize('path,position,attr,ocs', [
    ('/var/lib/univention-ldap/local-schema', 'cn=ldapschema,cn=univention', 'univentionLDAPSchemaFilename', 'univentionLDAPExtensionSchema'),
    ('/etc/univention/templates/files/etc/ldap/slapd.conf.d/', 'cn=ldapacl,cn=univention', 'univentionLDAPACLFilename', 'univentionLDAPExtensionACL'),
])
@pytest.mark.parametrize('name', ['etc/passwd3'])
def test_filename_validation(udm, lo, modify, prefix, path, position, attr, ocs, name):
    """Creates Schema and ACL extensions in invalid paths"""
    # bugs: [41780]
    def err(filename):
        return '%r exists (content=%r)' % (filename, open(filename).read())

    pos = '%s,%s' % (position, udm.LDAP_BASE)
    filename = filename_modify = '%s%s%s' % (prefix, name, strings.random_string())
    if modify:
        dn_modify = '%s=%s,%s' % (attr, ldap.dn.escape_dn_chars(filename), pos)
        filename = filename.replace('/', '').replace('.', '')
    dn = '%s=%s,%s' % (attr, ldap.dn.escape_dn_chars(filename), pos)
    fullpath = os.path.join(path, filename)
    fullpath_modify = os.path.join(path, filename_modify)
    attrs = {
        attr: [filename.encode('UTF-8')],
        'cn': [filename.encode('UTF-8')],
        'objectClass': [b'top', b'univentionObjectMetadata', ocs.encode('UTF-8')],
        'univentionOwnedByPackage': [b'foo'],
        'univentionOwnedByPackageVersion': [b'1'],
        attr.replace('Filename', 'Data'): [bz2.compress(b'\n' if modify else b'root:$6$5cAInBgG$7rdZuEujGK1QFoprcNspXsXHsymW3Txp0kDyHFsE.omI.3T0xek3KIneFPZ99Z8dwZnZ2I2O/Tk8x4mNNGSE4.:16965:0:99999:7:::')],
        attr.replace('Filename', 'Active'): [b'TRUE'],
    }
    al = [(key, list(val)) for key, val in attrs.items()]
    print(('Creating', dn))
    dn = lo.add(dn, al) or dn
    try:
        utils.wait_for_replication_and_postrun()
        if modify:
            assert os.path.exists(fullpath)
            if ocs == 'univentionLDAPExtensionACL':
                assert os.path.exists(fullpath + '.info')

            print(('Modifying into', dn_modify))
            dn = lo.modify(dn, [
                (attr, filename.encode('UTF-8'), filename_modify.encode('UTF-8')),
                ('cn', filename.encode('UTF-8'), filename_modify.encode('UTF-8')),
            ]) or dn
            print(('Modified', dn))
            assert dn == dn_modify
            utils.wait_for_replication_and_postrun()

        # object was renamed (if modify). make sure the old files do not exists anymore.
        assert not os.path.exists(fullpath_modify), err(fullpath_modify)
        assert not os.path.exists(fullpath), err(fullpath)
        if ocs == 'univentionLDAPExtensionACL':
            assert not os.path.exists(fullpath + '.info'), err(fullpath + '.info')
            assert not os.path.exists(fullpath_modify + '.info'), err(fullpath_modify + '.info')

        # create fake files and see if the listener would remove them.
        with open(fullpath_modify, 'w') as fd:
            fd.write('TEMP')
        if ocs == 'univentionLDAPExtensionACL':
            with open(fullpath_modify + '.info', 'w') as fd:
                fd.write('TEMP')
    finally:
        lo.delete(dn)

    utils.wait_for_replication_and_postrun()
    assert os.path.exists(fullpath_modify), err(fullpath_modify)
    assert 'TEMP' in err(fullpath_modify)
    os.unlink(fullpath_modify)
    if ocs == 'univentionLDAPExtensionACL':
        assert os.path.exists(fullpath_modify + '.info'), err(fullpath_modify)
        assert 'TEMP' in err(fullpath_modify + '.info')
        os.unlink(fullpath_modify + '.info')


class Bunch:
    """
    >>> y = Bunch(foo=42, bar='TEST')
    >>> print repr(y.foo), repr(y.bar)
    42 'TEST'

    >>> x = Bunch()
    >>> x.a = 4
    >>> print x.a
    4
    """

    def __init__(self, **kwds):
        self.__dict__.update(kwds)

    def __str__(self):
        result = []
        for key, value in self.__dict__.iteritems():
            result.append('%s=%r' % (key, value))
        return 'Bunch(' + ', '.join(result) + ')'

    def __repr__(self):
        return str(self)


@pytest.mark.tags('udm-ldapextensions', 'apptest')
@pytest.mark.roles('domaincontroller_master')
@pytest.mark.exposure('dangerous')
def test_create_portal_entry(udm, ucr):
    """Create a UMC portal entry"""
    portal = Bunch(
        name=uts.random_name(),
        displayName='"de_DE" "%s"' % (uts.random_name(),),
        logo=base64.b64encode(uts.random_name().encode('utf-8')).decode('ASCII'),
        background=base64.b64encode(uts.random_name().encode('utf-8')).decode('ASCII'),
    )

    kwargs = portal.__dict__.copy()
    kwargs['portalComputers'] = [ucr.get('ldap/hostdn')]

    dn = udm.create_object('portals/portal', **kwargs)
    utils.verify_ldap_object(dn, {
        'cn': [portal.name],
        'univentionNewPortalLogo': [portal.logo],
        'univentionNewPortalDisplayName': [portal.displayName.replace('"', '')],
        'univentionNewPortalBackground': [portal.background],
    })


@pytest.mark.roles('domaincontroller_master')
@pytest.mark.tags('udm-ldapextensions', 'apptest')
@pytest.mark.exposure('dangerous')
def test_create_data(udm, ucr):
    """Create a settings/data object"""
    data = uts.random_name(500)
    kwargs = {
        "position": 'cn=data,cn=univention,{}'.format(ucr['ldap/base']),
        "name": uts.random_name(),
        "filename": uts.random_name(),
        "description": uts.random_name(),
        "data_type": uts.random_name(),
        "data": base64.b64encode(bz2.compress(data.encode('UTF-8'))).decode('ASCII'),
        "ucsversionstart": uts.random_ucs_version(),
        "ucsversionend": uts.random_ucs_version(),
        "meta": [uts.random_name(), uts.random_name()],
        "package": uts.random_name(),
        "packageversion": uts.random_version(),
    }

    dn = udm.create_object('settings/data', **kwargs)

    utils.verify_ldap_object(
        dn,
        {
            'cn': [kwargs['name']],
            'description': [kwargs['description']],
            'univentionDataFilename': [kwargs['filename']],
            'univentionDataType': [kwargs['data_type']],
            'univentionData': [bz2.compress(data.encode('UTF-8'))],
            'univentionUCSVersionStart': [kwargs['ucsversionstart']],
            'univentionUCSVersionEnd': [kwargs['ucsversionend']],
            'univentionDataMeta': kwargs['meta'],
            'univentionOwnedByPackage': [kwargs['package']],
            'univentionOwnedByPackageVersion': [kwargs['packageversion']],
        },
    )


file_name = uts.random_name()
file_path = os.path.join('/tmp', file_name)


@pytest.fixture
def remove_tmp_file():
    yield
    try:
        os.remove(file_path)
    except OSError:
        pass


shutil.copy('/etc/hosts', file_path)
kwargs = {
    "data_type": uts.random_name(),
    "ucsversionstart": uts.random_ucs_version(),
    "ucsversionend": uts.random_ucs_version(),
    "meta": [uts.random_name(), uts.random_name()],
    "package": uts.random_name(),
    "packageversion": uts.random_version(),
}


def run_cmd(cmd):
    print(f'Running: {cmd!r}')
    cmd_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    cmd_out, cmd_err = cmd_proc.communicate()
    cmd_out, cmd_err = cmd_out.decode('UTF-8', 'replace'), cmd_err.decode('UTF-8', 'replace')
    print(f'exit code: {cmd_proc.returncode!r}')
    print(f'stdout:-----\n{cmd_out}\n-----')
    print(f'stderr:-----\n{cmd_err}\n-----')


@pytest.mark.roles('domaincontroller_master')
@pytest.mark.exposure('dangerous')
@pytest.mark.tags('udm-ldapextensions', 'apptest')
def test_register_data(udm, ucr, remove_tmp_file):
    """Register a settings/data object"""
    ldap_base = ucr['ldap/base']
    # make sure object is remove at the end
    dn = f'cn={file_name},cn=data,cn=univention,{ldap_base}'
    udm._cleanup.setdefault('settings/data', []).append(dn)
    register_cmd = [
        'ucs_registerLDAPExtension',
        '--binddn', 'cn=admin,{}'.format(ucr['ldap/base']),
        '--bindpwdfile', '/etc/ldap.secret',
        '--packagename', kwargs['package'],
        '--packageversion', kwargs['packageversion'],
        '--data', file_path,
        '--ucsversionstart', kwargs['ucsversionstart'],
        '--ucsversionend', kwargs['ucsversionend'],
        '--data_type', kwargs['data_type'],
        '--data_meta', kwargs['meta'][0],
        '--data_meta', kwargs['meta'][1],
    ]
    cmd = ['/bin/bash', '-c', 'source /usr/share/univention-lib/ldap.sh && {}'.format(' '.join([shlex.quote(x) for x in register_cmd]))]
    run_cmd(cmd)

    cmd = ['udm', 'settings/data', 'list', '--filter', f'cn={file_name}']
    print(f'Running {cmd!r}...')
    subprocess.call(cmd)

    with open(file_path) as fp:
        data = fp.read()

    utils.verify_ldap_object(
        dn,
        {
            'cn': [file_name],
            'description': [],  # ucs_registerLDAPExtension doesn't support description
            'univentionDataFilename': [file_name],
            'univentionDataType': [kwargs['data_type']],
            'univentionData': [bz2.compress(data.encode('UTF-8'))],
            'univentionUCSVersionStart': [kwargs['ucsversionstart']],
            'univentionUCSVersionEnd': [kwargs['ucsversionend']],
            'univentionDataMeta': kwargs['meta'],
            'univentionOwnedByPackage': [kwargs['package']],
            'univentionOwnedByPackageVersion': [kwargs['packageversion']],
        },
    )

    nums = kwargs['packageversion'].split('.')
    num0 = int(nums[0])
    num0 -= 1
    older_packageversion = '.'.join([str(num0)] + nums[1:])
    print('Registering with lower package version ({!r}) and changed "data_type"...'.format(kwargs['packageversion']))
    register_cmd = [
        'ucs_registerLDAPExtension',
        '--binddn', 'cn=admin,{}'.format(ucr['ldap/base']),
        '--bindpwdfile', '/etc/ldap.secret',
        '--packagename', kwargs['package'],
        '--packageversion', older_packageversion,
        '--data', file_path,
        '--ucsversionstart', kwargs['ucsversionstart'],
        '--ucsversionend', kwargs['ucsversionend'],
        '--data_type', uts.random_name(),
        '--data_meta', 'Some different meta data',
        '--data_meta', 'Some very different meta data',
    ]
    cmd = ['/bin/bash', '-c', 'source /usr/share/univention-lib/ldap.sh && {}'.format(' '.join([shlex.quote(x) for x in register_cmd]))]
    run_cmd(cmd)

    utils.verify_ldap_object(
        dn,
        {
            'cn': [file_name],
            'description': [],  # ucs_registerLDAPExtension does not support description
            'univentionDataFilename': [file_name],
            'univentionDataType': [kwargs['data_type']],
            'univentionData': [bz2.compress(data.encode('UTF-8'))],
            'univentionUCSVersionStart': [kwargs['ucsversionstart']],
            'univentionUCSVersionEnd': [kwargs['ucsversionend']],
            'univentionDataMeta': kwargs['meta'],
            'univentionOwnedByPackage': [kwargs['package']],
            'univentionOwnedByPackageVersion': [kwargs['packageversion']],
        },
    )
    print('OK: object unchanged.')


@pytest.mark.roles('domaincontroller_master')
@pytest.mark.exposure('dangerous')
def test_default_containers(ldap_base):
    """Check expected default containers"""
    udm_modules.update()
    expected_default_containers = {
        'mail/lists': [f'cn=domain,cn=mail,{ldap_base}', f'cn=mailinglists,cn=mail,{ldap_base}', f'cn=folder,cn=mail,{ldap_base}'],
        'dns/forward_zone': [f'cn=dns,{ldap_base}'],
        'portals/entry': [f'cn=entry,cn=portals,cn=univention,{ldap_base}'],
        'portals/portal': [f'cn=portal,cn=portals,cn=univention,{ldap_base}'],
        'portals/announcement': [f'cn=announcement,cn=portals,cn=univention,{ldap_base}'],
        'portals/category': [f'cn=category,cn=portals,cn=univention,{ldap_base}'],
        'portals/folder': [f'cn=folder,cn=portals,cn=univention,{ldap_base}'],
        'portals/all': [
            f'cn=portal,cn=portals,cn=univention,{ldap_base}',
            f'cn=entry,cn=portals,cn=univention,{ldap_base}',
            f'cn=category,cn=portals,cn=univention,{ldap_base}',
            f'cn=folder,cn=portals,cn=univention,{ldap_base}',
            f'cn=announcement,cn=portals,cn=univention,{ldap_base}',
        ],
        'groups/group': [f'cn=groups,{ldap_base}'],
        'dhcp/shared': [f'cn=dhcp,{ldap_base}'],
        'computers/domaincontroller_backup': [f'cn=dc,cn=computers,{ldap_base}'],
        'computers/windows': [f'cn=computers,{ldap_base}', f'cn=memberserver,cn=computers,{ldap_base}', f'cn=dc,cn=computers,{ldap_base}'],
        'computers/linux': [f'cn=computers,{ldap_base}', f'cn=memberserver,cn=computers,{ldap_base}', f'cn=dc,cn=computers,{ldap_base}'],
        'computers/memberserver': [f'cn=computers,{ldap_base}', f'cn=memberserver,cn=computers,{ldap_base}', f'cn=dc,cn=computers,{ldap_base}'],
        'computers/ipmanagedclient': [f'cn=computers,{ldap_base}', f'cn=memberserver,cn=computers,{ldap_base}', f'cn=dc,cn=computers,{ldap_base}'],
        'computers/macos': [f'cn=computers,{ldap_base}', f'cn=memberserver,cn=computers,{ldap_base}', f'cn=dc,cn=computers,{ldap_base}'],
        'computers/domaincontroller_master': [f'cn=dc,cn=computers,{ldap_base}'],
        'computers/computer': [f'cn=computers,{ldap_base}', f'cn=memberserver,cn=computers,{ldap_base}', f'cn=dc,cn=computers,{ldap_base}'],
        'computers/ubuntu': [f'cn=computers,{ldap_base}', f'cn=memberserver,cn=computers,{ldap_base}', f'cn=dc,cn=computers,{ldap_base}'],
        'computers/windows_domaincontroller': [f'cn=dc,cn=computers,{ldap_base}'],
        'computers/domaincontroller_slave': [f'cn=dc,cn=computers,{ldap_base}'],
        'computers/trustaccount': [f'cn=computers,{ldap_base}', f'cn=memberserver,cn=computers,{ldap_base}', f'cn=dc,cn=computers,{ldap_base}'],
        'networks/network': [f'cn=networks,{ldap_base}'],
        'users/self': [f'cn=users,{ldap_base}'],
        'users/passwd': [f'cn=users,{ldap_base}'],
        'users/user': [f'cn=users,{ldap_base}'],
        'users/contact': [f'cn=users,{ldap_base}'],
        'appcenter/app': [f'cn=apps,cn=univention,{ldap_base}'],
        'settings/portal': [f'cn=portal,cn=univention,{ldap_base}'],
        'settings/data': [f'cn=data,cn=univention,{ldap_base}'],
        'settings/portal_category': [f'cn=categories,cn=portal,cn=univention,{ldap_base}'],
        'settings/portal_entry': [f'cn=portal,cn=univention,{ldap_base}'],
        'shares/printergroup': [f'cn=printers,{ldap_base}'],
        'shares/printer': [f'cn=printers,{ldap_base}'],
        'shares/share': [f'cn=shares,{ldap_base}'],
        'shares/print': [f'cn=printers,{ldap_base}'],

    }
    lo, position = uldap.getAdminConnection()
    for module_name in udm_modules.modules.keys():
        module = udm_modules.get(module_name)
        udm_modules.init(lo, position, module)
        obj = module.object(None, lo, position)
        default_containers = obj.get_default_containers(lo)
        if module_name in expected_default_containers:
            assert set(expected_default_containers[module_name]).issubset(default_containers), f'mismatch for module {module_name}'


@pytest.mark.roles('domaincontroller_master')
@pytest.mark.exposure('dangerous')
def test_default_containers_extended_attribute(ldap_base, udm):
    name = uts.random_name()
    default_container1 = uts.random_name()
    default_container2 = uts.random_name()
    expected_containers = [default_container1, default_container2]
    properties = {
        'name': name,
        'shortDescription': uts.random_string(),
        'CLIName': name,
        'module': 'settings/directory',
        'objectClass': 'univentionFreeAttributes',
        'ldapMapping': 'univentionFreeAttribute19',
        'multivalue': '1',
        'mayChange': 1,
        'deleteObjectClass': 1,
    }
    udm.stop_cli_server()
    udm.create_object('settings/extended_attribute', position=udm.UNIVENTION_CONTAINER, **properties)
    setting_dn = f'cn=default containers,{udm.UNIVENTION_CONTAINER}'
    udm.stop_cli_server()
    try:
        cmd = ['udm', 'settings/directory', 'modify', f'--dn={setting_dn}', '--append', f'{name}={default_container1}', '--append', f'{name}={default_container2}']
        subprocess.check_call(cmd)
        lo, position = uldap.getAdminConnection()
        udm_modules.update()
        users = udm_modules.get('users/user')
        users.object.default_containers_attribute_name = name
        udm_modules.init(lo, position, users)
        containers = users.object.get_default_containers(lo)
        assert set(containers) == set(expected_containers)
    finally:
        cmd = ['udm', 'settings/directory', 'modify', f'--dn={setting_dn}', '--remove', f'{name}={default_container1}', '--remove', f'{name}={default_container2}']
        subprocess.check_call(cmd)
