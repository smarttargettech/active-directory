#!/usr/share/ucs-test/runner python3
## desc: Quota share cache; rename share
## roles-not: [basesystem]
## exposure: dangerous
## packages:
##   - univention-quota

import subprocess

import ldap

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils

import quota_cache as qc


SHARE_CACHE_DIR = '/var/cache/univention-quota/'


def create_share(host):
    name = uts.random_name()
    path = '/mnt/_%s' % name
    return udm.create_object('shares/share', name=name, path=path, host=host)


def rename_share(dn):
    name = uts.random_name()
    udm.modify_object('shares/share', dn=dn, name=name)
    exploded_dn = ldap.explode_dn(dn)
    exploded_dn[0] = 'cn=%s' % name
    return ','.join(exploded_dn)


if __name__ == '__main__':
    ucr = ucr_test.UCSTestConfigRegistry()
    ucr.load()

    my_fqdn = '%(hostname)s.%(domainname)s' % ucr

    with udm_test.UCSTestUDM() as udm:
        share1 = create_share(my_fqdn)

        utils.wait_for_replication_and_postrun()

        qc.cache_must_exists(share1)

        share2 = rename_share(share1)

        utils.wait_for_replication_and_postrun()

        qc.cache_must_not_exists(share1)
        qc.cache_must_exists(share2)

        # renamed objects must be removed manually
        subprocess.call('udm-test shares/share remove --dn "%s"' % share2, shell=True)

    utils.wait_for_replication_and_postrun()

    qc.cache_must_not_exists(share1)
    qc.cache_must_not_exists(share2)
