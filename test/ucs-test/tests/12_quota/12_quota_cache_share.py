#!/usr/share/ucs-test/runner python3
## desc: Quota share cache; create and remove shares
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


if __name__ == '__main__':
    ucr = ucr_test.UCSTestConfigRegistry()
    ucr.load()

    my_fqdn = '%(hostname)s.%(domainname)s' % ucr

    with udm_test.UCSTestUDM() as udm:
        share1 = create_share(my_fqdn)
        share2 = create_share('test.bar')

        utils.wait_for_replication_and_postrun()

        qc.cache_must_exists(share1)
        qc.cache_must_not_exists(share2)

    utils.wait_for_replication_and_postrun()

    qc.cache_must_not_exists(share1)
    qc.cache_must_not_exists(share2)
