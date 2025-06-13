#!/usr/share/ucs-test/runner python3
## desc: Quota share cache; modify share host
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


def create_share(host):
    name = uts.random_name()
    path = '/mnt/_%s' % name
    return udm.create_object('shares/share', name=name, path=path, host=host)


def change_host(dn, host):
    udm.modify_object('shares/share', dn=dn, host=host)


if __name__ == '__main__':
    ucr = ucr_test.UCSTestConfigRegistry()
    ucr.load()

    my_fqdn = '%(hostname)s.%(domainname)s' % ucr

    with udm_test.UCSTestUDM() as udm:
        share1 = create_share(my_fqdn)
        share2 = create_share('test.bar')
        share3 = create_share('test2.bar')

        utils.wait_for_replication_and_postrun()

        qc.cache_must_exists(share1)
        qc.cache_must_not_exists(share2)
        qc.cache_must_not_exists(share3)

        change_host(share1, 'test.bar')
        change_host(share2, my_fqdn)
        change_host(share3, 'foo.bar')

        utils.wait_for_replication_and_postrun()

        qc.cache_must_not_exists(share1)
        qc.cache_must_exists(share2)
        qc.cache_must_not_exists(share3)

    utils.wait_for_replication_and_postrun()

    qc.cache_must_not_exists(share1)
    qc.cache_must_not_exists(share2)
    qc.cache_must_not_exists(share3)
