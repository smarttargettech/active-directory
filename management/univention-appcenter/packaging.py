# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# SPDX-FileCopyrightText: 2024-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from debian.changelog import Changelog
from debian.deb822 import Deb822
from setuptools import setup as orig_setup


def _get_version():
    changelog = Changelog(open('debian/changelog', encoding='utf-8'))
    return changelog.full_version.split('A~')[0]


def _get_description(name):
    for package in Deb822.iter_paragraphs(open('debian/control', encoding='utf-8')):
        if package.get('Package') == name:
            description = package['Description']
            return description.split('\n .\n')[0]


def setup(name, **attrs):
    if 'name' not in attrs:
        attrs['name'] = name
    if 'license' not in attrs:
        attrs['license'] = 'AGPL'
    if 'author_email' not in attrs:
        attrs['author_email'] = 'packages@univention.de'
    if 'author' not in attrs:
        attrs['author'] = 'Univention GmbH'
    if 'url' not in attrs:
        attrs['url'] = 'https://www.univention.de/'
    if 'version' not in attrs:
        attrs['version'] = _get_version()
    if 'description' not in attrs:
        attrs['description'] = _get_description(name)
    return orig_setup(**attrs)
