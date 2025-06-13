#!/usr/share/ucs-test/runner python3
## desc: Tests the Univention Admin Diary
## tags: [apptest]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - univention-admin-diary-backend


import univention.admindiary.backend
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.config_registry import handler_set


def main():
    with ucr_test.UCSTestConfigRegistry(), udm_test.UCSTestUDM() as udm, univention.admindiary.backend.get_client(version=1) as client:
        limit = 2
        for _ in range(limit + 1):
            udm.create_user()
        handler_set(["admin/diary/query/limit=0"])
        len_without_limit = len(client.query())
        handler_set(["admin/diary/query/limit=%s" % limit])
        len_with_limit = len(client.query())
        assert len_with_limit == limit, 'The length of the query result is not that of admin/diary/query/limit'
        assert len_with_limit != len_without_limit, 'The length of the query result without a limit and with a limit of %s are the same. Functionality of limit cannot be tested'


if __name__ == '__main__':
    main()
