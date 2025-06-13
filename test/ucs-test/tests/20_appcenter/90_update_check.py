#!/usr/share/ucs-test/runner python3
## desc: update-check test
## packages:
##   - univention-appcenter
## bugs: [52771]
## tags: [appcenter]

from unittest import mock

import univention.appcenter
from univention.appcenter.actions import get_action


def mock_ucr_get(var):
    if var == 'version/version':
        return '4.4'
    raise  # noqa: PLE0704


# new app cache
def get_every_single_app():
    return [
        mock.Mock(
            name='component_yes',
            id='component_yes',
            component_id='component_yes',
        ),
        mock.Mock(
            name='package_yes',
            id='package_yes',
            component_id='package_yes',
        ),
    ]


# current apps
def get_all_locally_installed_apps():
    return [
        mock.Mock(
            id='docker_yes',
            name='docker_yes',
            component_id='docker_yes',
            docker=True,
            supported_ucs_versions=['2.2-2', '5.0-0', '1.1-1'],
        ),
        mock.Mock(
            id='docker_no',
            name='docker_no',
            component_id='docker_no',
            docker=True,
            supported_ucs_versions=['2.2-2', '1.1-1'],
        ),
        mock.Mock(
            id='component_yes',
            name='component_yes',
            component_id='component_yes',
            docker=False,
            without_repository=True,
        ),
        mock.Mock(
            id='component_no',
            name='component_no',
            component_id='component_no',
            docker=False,
            without_repository=True,
        ),
        mock.Mock(
            id='package_no',
            name='package_no',
            component_id='package_no',
            docker=False,
            without_repository=False,
        ),
        mock.Mock(
            id='package_yes',
            name='package_yes',
            component_id='package_yes',
            docker=False,
            without_repository=False,
        ),

    ]


@mock.patch('univention.appcenter.ucr.ucr_get', side_effect=mock_ucr_get)
@mock.patch('univention.appcenter.app_cache.AppCenterCache.get_every_single_app', side_effect=get_every_single_app)
@mock.patch('univention.appcenter.app_cache.Apps.get_all_locally_installed_apps', side_effect=get_all_locally_installed_apps)
def test_update_check(a, b, c):
    update_check = get_action('update-check')
    with mock.patch.object(univention.appcenter.actions.umc_update.Update, 'main', return_value=None):
        # check apps
        a = update_check.get_blocking_apps(ucs_version='5.0')
        assert {'package_no', 'component_no', 'docker_no'} == set(a.keys()), set(a.keys())
        # no check if "new" version is "older"
        a = update_check.get_blocking_apps(ucs_version='3.0')
        assert bool(a) is False, a
        a = update_check.get_blocking_apps(ucs_version='4.4')
        assert bool(a) is False, a
        # check for newer minor version
        a = update_check.get_blocking_apps(ucs_version='4.5')
        assert bool(a) is True, a


if __name__ == '__main__':
    test_update_check()
