#!/usr/bin/python3
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2020-2025 Univention GmbH
#
# https://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <https://www.gnu.org/licenses/>.

import sys
from unittest.mock import MagicMock

import pytest
from univentionunittests import import_module


def pytest_addoption(parser):
    parser.addoption("--installed-lib", action="store_true", help="Test against installed Python lib installation (not src)")


def import_lib_module(request, name):
    use_installed = request.config.getoption('--installed-lib')
    return import_module(name, 'python/', f'univention.lib.{name}', use_installed=use_installed)


@pytest.fixture(scope='session')
def atjobs(request):
    return import_lib_module(request, "atjobs")


@pytest.fixture(scope='session')
def fstab(request):
    return import_lib_module(request, 'fstab')


@pytest.fixture(scope='session')
def i18n(request):
    return import_lib_module(request, 'i18n')


@pytest.fixture(scope='session')
def listenerSharePath(request):
    return import_lib_module(request, 'listenerSharePath')


@pytest.fixture(scope='session')
def locking(request):
    return import_lib_module(request, 'locking')


@pytest.fixture(scope='session')
def misc(request):
    sys.modules['univention.uldap'] = MagicMock()
    import_lib_module(request, 'ucs')
    return import_lib_module(request, 'misc')


@pytest.fixture(scope='session')
def ucrLogrotate(request):
    return import_lib_module(request, 'ucrLogrotate')


@pytest.fixture(scope='session')
def ucs(request):
    return import_lib_module(request, 'ucs')


@pytest.fixture(scope='session')
def umc_module(request):
    return import_lib_module(request, 'umc_module')


@pytest.fixture(scope='session')
def umc(request):
    return import_lib_module(request, 'umc')
