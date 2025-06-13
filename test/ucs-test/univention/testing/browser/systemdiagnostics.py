#!/usr/bin/python3
#
# -*- coding: utf-8 -*-
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2023-2025 Univention GmbH
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

from playwright.sync_api import Page, expect

from univention.lib.i18n import Translation
from univention.testing.browser.lib import MIN, UMCBrowserTest


_ = Translation('ucs-test-framework').translate


class SystemDiagnostic:
    def __init__(self, tester: UMCBrowserTest):
        self.tester: UMCBrowserTest = tester
        self.page: Page = tester.page
        self.module_name = _('System diagnostic')

    def navigate(self, username='Administrator', password='univention'):
        self.tester.login(username, password)
        self.tester.open_module(self.module_name)

        self.wait_for_system_diagnostics_to_finish()

    def run_system_diagnostics(self):
        self.page.get_by_role('button', name=_('Run system diagnosis')).click()
        self.wait_for_system_diagnostics_to_finish()

    def wait_for_system_diagnostics_to_finish(self):
        progress_bar = self.page.get_by_role('progressbar')
        try:
            expect(progress_bar).to_be_visible(timeout=1 * MIN)
            expect(progress_bar).to_be_hidden(timeout=5 * MIN)
        except AssertionError:
            pass
