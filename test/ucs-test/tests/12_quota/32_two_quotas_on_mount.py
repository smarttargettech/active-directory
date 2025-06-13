#!/usr/share/ucs-test/runner pytest-3 -svvv
## desc: Test setting two different quotas on the same mountpoint
## roles-not: [basesystem]
## exposure: dangerous
## packages:
##   - univention-quota

from quota_test import QuotaCheck


def test_nonzero():
    print("Checking if setting of Quota works with two shares on a mountpoint, with none of the values being zero.")
    for fs_type in ['ext4', 'xfs']:
        print(f"Now checking fs type: {fs_type}")
        quotaCheck = QuotaCheck(quota_type="usrquota", fs_type=fs_type)
        quota_policies = [{
            'name': 'quota_policy1',
            'spaceSoftLimit': str(1026 ** 2),
            'spaceHardLimit': str(2048 ** 2),
            'inodeSoftLimit': '3',
            'inodeHardLimit': '4',
            'reapplyQuota': 'TRUE',
        }, {
            'name': 'quota_policy2',
            'spaceSoftLimit': str(1024 ** 2),
            'spaceHardLimit': str(4096 ** 2),
            'inodeSoftLimit': '5',
            'inodeHardLimit': '7',
            'reapplyQuota': 'TRUE',
        }]

        expected_result = {
            'bsoft': 1,
            'bhard': 4,
            'fsoft': 3,
            'fhard': 4,
        }

        quotaCheck.test_two_shares_on_one_mount(quota_policies, expected_result)


def test_zero():
    print("Checking if setting of Quota works with two shares on a mountpoint, with some of the values being zero.")
    for fs_type in ['ext4', 'xfs']:
        print(f"Now checking fs type: {fs_type}")
        quotaCheck = QuotaCheck(quota_type="usrquota", fs_type=fs_type)
        quota_policies = [{
            'name': 'quota_policy1',
            'spaceSoftLimit': '0',
            'spaceHardLimit': str(2048 ** 2),
            'inodeSoftLimit': '0',
            'inodeHardLimit': '4',
            'reapplyQuota': 'TRUE',
        }, {
            'name': 'quota_policy2',
            'spaceSoftLimit': str(1024 ** 2),
            'spaceHardLimit': '0',
            'inodeSoftLimit': '0',
            'inodeHardLimit': '0',
            'reapplyQuota': 'TRUE',
        }]

        expected_result = {
            'bsoft': 1,
            'bhard': 4,
            'fsoft': 0,
            'fhard': 4,
        }

        quotaCheck.test_two_shares_on_one_mount(quota_policies, expected_result)


def test_one_policy():
    print("Checking if setting of Quota works with two shares on a mountpoint, with only one of them having a quota policy attached.")
    for fs_type in ['ext4', 'xfs']:
        print(f"Now checking fs type: {fs_type}")
        quotaCheck = QuotaCheck(quota_type="usrquota", fs_type=fs_type)
        quotaCheck.test_two_shares_on_one_mount_only_one_policy()
