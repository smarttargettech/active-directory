#!/usr/share/ucs-test/runner python3
## desc: Quota share cache; create different policies
## roles-not: [basesystem]
## exposure: dangerous
## packages:
##   - univention-quota

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils

import quota_cache as qc


SHARE_CACHE_DIR = '/var/cache/univention-quota/'


def create_share(position):
    my_fqdn = '%(hostname)s.%(domainname)s' % ucr
    name = uts.random_name()
    path = '/mnt/_%s' % name
    return udm.create_object('shares/share', name=name, path=path, host=my_fqdn, position=position)


def create_policy(inodeSoftLimit, inodeHardLimit, spaceSoftLimit, spaceHardLimit, reapplyQuota):
    name = uts.random_name()
    position = 'cn=userquota,cn=shares,cn=policies,%s' % ucr.get('ldap/base')
    return udm.create_object(
        'policies/share_userquota', position=position, name=name,
        softLimitSpace=spaceSoftLimit,
        hardLimitSpace=spaceHardLimit,
        softLimitInodes=inodeSoftLimit,
        hardLimitInodes=inodeHardLimit,
        reapplyeverylogin=reapplyQuota)


def append_policy(dn, udm_type, policy):
    udm.modify_object(udm_type, dn=dn, policy_reference=policy)


if __name__ == '__main__':
    ucr = ucr_test.UCSTestConfigRegistry()
    ucr.load()

    with udm_test.UCSTestUDM() as udm:
        ou_dn = udm.create_object('container/ou', name=uts.random_name())
        share1 = create_share(ou_dn)

        container_dn = udm.create_object('container/cn', name=uts.random_name(), position=ou_dn)
        share2 = create_share(container_dn)

        utils.wait_for_replication_and_postrun()

        qc.cache_must_exists(share1)
        qc.cache_must_exists(share2)

        inodeSoftLimit_policy1 = '10'
        inodeHardLimit_policy1 = '15'
        spaceSoftLimit_policy1 = '10MB'
        spaceHardLimit_policy1 = '20MB'
        reapplyQuota_policy1 = 'FALSE'
        policy1 = create_policy(inodeSoftLimit_policy1, inodeHardLimit_policy1, spaceSoftLimit_policy1, spaceHardLimit_policy1, reapplyQuota_policy1)
        append_policy(ou_dn, 'container/ou', policy1)
        utils.wait_for_replication_and_postrun()

        print('Check values for %s' % share1)
        qc.check_values(share1, inodeSoftLimit_policy1, inodeHardLimit_policy1, spaceSoftLimit_policy1, spaceHardLimit_policy1, reapplyQuota_policy1)
        print('Check values for %s' % share2)
        qc.check_values(share2, inodeSoftLimit_policy1, inodeHardLimit_policy1, spaceSoftLimit_policy1, spaceHardLimit_policy1, reapplyQuota_policy1)

        inodeSoftLimit_policy2 = None
        inodeHardLimit_policy2 = None
        spaceSoftLimit_policy2 = '40MB'
        spaceHardLimit_policy2 = '80MB'
        reapplyQuota_policy2 = 'TRUE'
        policy2 = create_policy(inodeSoftLimit_policy2, inodeHardLimit_policy2, spaceSoftLimit_policy2, spaceHardLimit_policy2, reapplyQuota_policy2)
        append_policy(container_dn, 'container/cn', policy2)
        utils.wait_for_replication_and_postrun()

        print('Check values for %s' % share1)
        qc.check_values(share1, inodeSoftLimit_policy1, inodeHardLimit_policy1, spaceSoftLimit_policy1, spaceHardLimit_policy1, reapplyQuota_policy1)
        print('Check values for %s' % share2)
        qc.check_values(share2, inodeSoftLimit_policy1, inodeHardLimit_policy1, spaceSoftLimit_policy2, spaceHardLimit_policy2, reapplyQuota_policy2)

        inodeHardLimit_policy1 = '30'
        udm.modify_object('policies/share_userquota', dn=policy1, hardLimitInodes=inodeHardLimit_policy1)
        utils.wait_for_replication_and_postrun()

        print('Check values for %s' % share1)
        qc.check_values(share1, inodeSoftLimit_policy1, inodeHardLimit_policy1, spaceSoftLimit_policy1, spaceHardLimit_policy1, reapplyQuota_policy1)
        print('Check values for %s' % share2)
        qc.check_values(share2, inodeSoftLimit_policy1, inodeHardLimit_policy1, spaceSoftLimit_policy2, spaceHardLimit_policy2, reapplyQuota_policy2)

    utils.wait_for_replication_and_postrun()

    qc.cache_must_not_exists(share1)
    qc.cache_must_not_exists(share2)
