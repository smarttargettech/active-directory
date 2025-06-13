#!/usr/share/ucs-test/runner python3
## desc: |
##  Check the UMC query command with a custom INI file.
## roles-not: [basesystem]
## packages:
##   - univention-management-console-module-appcenter
## tags: [appcenter]
## exposure: safe
## bugs: [44768]

import os
import sys

import univention.testing.strings as str_test
import univention.testing.ucr as ucr_test
from univention import config_registry
from univention.appcenter.app_cache import AppCache
from univention.testing.umc import Client

import appcentertest as app_test


opened_files = []


def open_file(prefix, suffix):
    path = f'{prefix}.{suffix}'
    opened_files.append(path)
    return open(path, 'w')


def cleanup():
    print('')
    print('Removing temporarily created files...')
    for ipath in opened_files:
        if os.path.exists(ipath):
            os.unlink(ipath)


def get_temp_app_prefix(app_cache):
    return f'{app_cache.get_cache_dir()}/testapp_{str_test.random_name()}'


def write_ini_file(app_prefix):
    print('Writing INI file: %s.ini' % os.path.basename(app_prefix))
    with open_file(app_prefix, 'ini') as ini_file:
        ini_file.write('''
[Application]
ID=test_app
Code=00
Name=Test App
Version=11
License=freemium
Description=Test App [EN]

[de]
Description=Test App [DE]
''')


def test_ini_data(umc_data, lang):
    sys.stdout.write('Testing INI file entries for correctness... ')
    sys.stdout.flush()
    expected_data = {
        'id': 'test_app',
        'code': '00',
        'name': 'Test App',
        'version': '11',
        'license': 'freemium',
        'description': 'Test App [%s]' % lang,
    }
    for ikey, ival in expected_data.items():
        expected_val = expected_data[ikey]  # noqa: PLR1733
        assert umc_data[ikey] == ival, f'Entry {ikey}={ival} does not match expected value {expected_val}!'
    print('SUCCESS')


README_TYPES = (
    'README',
    'README_INSTALL',
    'README_POST_INSTALL',
    'README_UPDATE',
    'README_POST_UPDATE',
    'README_UNINSTALL',
    'README_POST_UNINSTALL',
)


def write_readme_file(app_prefix, readme_filename):
    with open_file(app_prefix, readme_filename) as readme_file:
        readme_file.write('--%s--' % readme_filename)


def write_readme_files(app_prefix):
    print('Writing README files:')
    for readme in README_TYPES:
        for lang in ('EN', 'DE'):
            filename = f'{readme}_{lang}'
            print('  %s' % filename)
            write_readme_file(app_prefix, filename)


def test_readme_files(umc_data, lang):
    sys.stdout.write('Testing README file entries for correctness... ')
    sys.stdout.flush()
    for readme in README_TYPES:
        expected_val = f'--{readme}_{lang}--'
        val = umc_data[readme.lower()]
        assert val == expected_val, f'Entry {readme}={val} does not match expected value {expected_val}!'
    print('SUCCESS')


RATINGS = (
    'VendorSupported',
    'EditorsAward',
    'PopularityAward',
)


def write_ratings(app_prefix, *keys):
    print('Writing new META file')
    with open_file(app_prefix, 'meta') as meta_file:
        meta_file.write('[Application]\n')
        for ikey in keys:
            meta_file.write('%s=1\n' % ikey)


def get_ratings(umc_data):
    ratings = set()
    for irating in umc_data.get('rating', []):
        if irating['value'] == 1:
            ratings.add(irating['name'])
    return ratings


def test_ratings(umc_data, *keys):
    sys.stdout.write(f'Testing rating {keys} in meta file for correctness... ')
    sys.stdout.flush()
    assert set(keys) == get_ratings(umc_data), f'Ratings {get_ratings(umc_data)} do not match expected value {set(keys)}!'
    print('SUCCESS')


def get_app_from_umc(lang='en_US'):
    # UMC query
    client = Client.get_test_connection(language=lang)
    apps = client.umc_command('appcenter/query', print_response=False, print_request_data=False).result

    # pick our test app from the list of all apps
    matches = [iapp for iapp in apps if iapp['id'] == 'test_app']
    assert len(matches) > 0, 'The test app does not occur in the list of queried apps!'
    return matches[0]


def test_all():
    cache = AppCache()
    cache.clear_cache()
    app_prefix = get_temp_app_prefix(cache)
    write_ini_file(app_prefix)
    write_readme_files(app_prefix)

    # test English and German localization
    for lang in ('en_US', 'de_DE'):
        lang_suffix = lang.split('_')[0].upper()
        print('')
        print('Testing language: %s' % lang_suffix)

        # test INI and README file data
        app = get_app_from_umc(lang)
        test_ini_data(app, lang_suffix)
        test_readme_files(app, lang_suffix)

    # test ratings for a few combinations
    for rating in (
            (RATINGS[0], RATINGS[2]),
            (RATINGS[1],),
            (RATINGS[0], RATINGS[1], RATINGS[2]),
    ):
        cache.clear_cache()
        write_ratings(app_prefix, *rating)
        app = get_app_from_umc()
        test_ratings(app, *rating)


if __name__ == '__main__':
    with ucr_test.UCSTestConfigRegistry() as ucr:
        # make sure that the app center cache dir is not resynced during the test
        # ... this allows us to add our test app data directly to the cache dir
        config_registry.handler_set(['appcenter/umc/update/always=false'])
        try:
            app_test.restart_umc()
            test_all()
        finally:
            app_test.restart_umc()
            cleanup()
