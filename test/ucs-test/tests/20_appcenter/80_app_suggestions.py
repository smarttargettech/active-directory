#!/usr/share/ucs-test/runner python3
## desc: |
##  Test appcenter/suggestions call
## roles-not: [basesystem]
## packages:
##   - univention-management-console-module-appcenter
## tags: [appcenter]
## exposure: safe

from univention.testing.umc import Client

import appcentertest as app_test


if __name__ == '__main__':
    client = Client.get_test_connection()
    client.umc_command('appcenter/suggestions', {'version': 'v1'})
    app_test.restart_umc()
