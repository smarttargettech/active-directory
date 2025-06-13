#!/usr/share/ucs-test/runner python3
## desc: Create a valid full appcenter/app object
## tags: [SKIP-UCSSCHOOL,udm-ldapextensions,apptest]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
## - univention-management-console-module-appcenter

import base64

import univention.testing.strings as uts
import univention.testing.udm as udm_test
from univention.config_registry import ConfigRegistry
from univention.testing import utils


if __name__ == '__main__':
    ucr = ConfigRegistry()
    ucr.load()

    with udm_test.UCSTestUDM() as udm:
        id = uts.random_name()
        name = uts.random_name()
        version = uts.random_name()
        shortDescription = [uts.random_name(), uts.random_name()]
        longDescription = [uts.random_name(), uts.random_name()]
        vendor = uts.random_name()
        contact = uts.random_name()
        maintainer = uts.random_name()
        website = [uts.random_name(), uts.random_name()]
        websiteVendor = [uts.random_name(), uts.random_name()]
        websiteMaintainer = [uts.random_name(), uts.random_name()]
        icon = base64.encodebytes(uts.random_name().encode('utf-8')).decode('ascii')
        category = uts.random_name()
        webInterface = uts.random_name()
        webInterfaceName = uts.random_name()
        conflictingApps = [uts.random_name(), uts.random_name()]
        conflictingSystemPackages = [uts.random_name(), uts.random_name()]
        defaultPackages = [uts.random_name(), uts.random_name()]
        defaultPackagesMaster = [uts.random_name(), uts.random_name()]
        umcModuleName = uts.random_name()
        umcModuleFlavor = uts.random_name()
        serverRole = ['domaincontroller_master', 'domaincontroller_backup', 'domaincontroller_slave', 'memberserver']
        server = ['server1.foo.bar', 'server2.foo.bar']

        app = udm.create_object(
            'appcenter/app',
            position=udm.UNIVENTION_CONTAINER,
            id=id,
            name=name,
            version=version,
            shortDescription=shortDescription,
            longDescription=longDescription,
            vendor=vendor,
            contact=contact,
            maintainer=maintainer,
            website=website,
            websiteVendor=websiteVendor,
            websiteMaintainer=websiteMaintainer,
            icon=icon,
            category=category,
            webInterface=webInterface,
            webInterfaceName=webInterfaceName,
            conflictingApps=conflictingApps,
            conflictingSystemPackages=conflictingSystemPackages,
            defaultPackages=defaultPackages,
            defaultPackagesMaster=defaultPackagesMaster,
            umcModuleName=umcModuleName,
            umcModuleFlavor=umcModuleFlavor,
            serverRole=serverRole,
            server=server,
        )
        utils.verify_ldap_object(app, {
            'univentionAppName': [name],
            'univentionAppID': [id],
            'univentionAppVersion': [version],
            'univentionAppDescription': shortDescription,
            'univentionAppLongDescription': longDescription,
            'univentionAppVendor': [vendor],
            'univentionAppContact': [contact],
            'univentionAppMaintainer': [maintainer],
            'univentionAppWebsite': website,
            'univentionAppWebsiteVendor': websiteVendor,
            'univentionAppWebsiteMaintainer': websiteMaintainer,
            'univentionAppIcon': [icon],
            'univentionAppCategory': [category],
            'univentionAppWebInterface': [webInterface],
            'univentionAppWebInterfaceName': [webInterfaceName],
            'univentionAppConflictingApps': conflictingApps,
            'univentionAppConflictingSystemPackages': conflictingSystemPackages,
            'univentionAppDefaultPackages': defaultPackages,
            'univentionAppDefaultPackagesMaster': defaultPackagesMaster,
            'univentionAppUMCModuleName': [umcModuleName],
            'univentionAppUMCModuleFlavor': [umcModuleFlavor],
            'univentionAppServerRole': serverRole,
            'univentionAppInstalledOnServer': server,

        })

        udm.remove_object('appcenter/app', dn=app)
        utils.verify_ldap_object(app, {
            'univentionAppName': [name],
        }, should_exist=False)
