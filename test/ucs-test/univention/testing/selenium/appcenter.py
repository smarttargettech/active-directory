#!/usr/bin/python3
#
# Selenium Tests
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2017-2025 Univention GmbH
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

from time import sleep
from typing import Any

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By

from univention.admin import localization
from univention.testing.selenium.utils import expand_path


translator = localization.translation('ucs-test-framework')
_ = translator.translate


class AppCenter:

    def __init__(self, selenium: Any) -> None:
        self.selenium = selenium

    def install_app(self, app_name: str) -> None:
        # TODO: Make sure the license is activated!
        self.open_app(app_name)

        self.selenium.click_button(_('Install'))

        # ChooseHostWizard
        try:
            self.selenium.wait_for_text(_('In order to proceed with the installation'), timeout=20)
        except TimeoutException:
            pass
        else:
            self.selenium.click_button(_('Continue'))
        self.selenium.wait_until_all_standby_animations_disappeared()

        try:
            self.selenium.wait_for_any_text_in_list([_('Accept license'), _('Next'), _('Continue anyway'), _('Install app'), _('Install anyway'), _('Start installation')])
            install_clicked = False
            x = 0
            max_pages = 6
            while not install_clicked and x < max_pages:
                x += 1
                try:
                    self.selenium.click_buttons([_('Accept license'), _('Next'), _('Continue anyway')], timeout=0)
                except TimeoutException:
                    pass
                else:
                    continue
                try:
                    self.selenium.click_buttons([_('Install app'), _('Install anyway'), _('Start installation')], timeout=0)
                    install_clicked = True
                except TimeoutException:
                    pass
                else:
                    continue
        except TimeoutException:
            pass
        finally:
            # header of progress bar
            self.selenium.wait_for_any_text_in_list([_('Installing'), 'Installiere'])

        self.selenium.wait_for_any_text_in_list([_('Install Information'), _('Uninstall'), _('Manage domain wide installations'), _('Manage installations'), _('Manage installation')], timeout=900)
        # readme install
        try:
            self.selenium.click_button(_('Back to overview'), timeout=1)
        except TimeoutException:
            pass
        self.selenium.wait_until_all_standby_animations_disappeared()

    def uninstall_app(self, app_name: str) -> None:
        self.open_app(app_name)
        self.selenium.click_buttons([_('Manage installations'), _('Manage installation')], timeout=10)
        try:
            self.selenium.click_element("//*[contains(text(), 'this computer')]", right_click=True)
            self.selenium.click_element(expand_path('//td[@containsClass="dijitMenuItemLabel"][text() = "Uninstall"]'))
        except TimeoutException:
            self.selenium.click_button(_('Uninstall'))
        self.selenium.wait_for_text(_('Running tests'))
        self.selenium.wait_for_text(_('Start removal'))
        self.selenium.click_button(_('Start removal'))

        self.selenium.wait_for_text(_('Install'))
        self.selenium.wait_until_all_standby_animations_disappeared()

    def upgrade_app(self, app: str) -> None:
        self.open_app(app)

        self.selenium.click_text(_('(this computer)'))
        self.selenium.click_button(_('Upgrade'))

        try:
            self.selenium.wait_for_text(_('Upgrade Information'), timeout=5)
        except TimeoutException:
            pass
        else:
            self.selenium.click_button(_('Upgrade'), xpath_prefix=expand_path('//[@containsClass="dijitDialog"]'))

        self.selenium.wait_until_progress_bar_finishes()
        self.selenium.wait_for_text(_('Upgrade of %s') % (app,))
        self.selenium.click_button(_('Upgrade'))
        self.selenium.wait_until_progress_bar_finishes(timeout=900)
        self.selenium.wait_for_text(_('More information'), timeout=900)

    def search_for_apps(self, text: str, category: str = "") -> None:
        self.open()

        category = category or _('All')
        self.select_search_category(category)

        search_field = self.selenium.driver.find_element(
            By.XPATH,
            '//*[contains(text(), "%s")]/../input' % ('Search applications...',),
        )
        search_field.send_keys(text)
        sleep(2)

        return self.selenium.get_gallery_items()

    def select_search_category(self, category: str) -> None:
        self.selenium.show_notifications(False)
        self.selenium.click_element(
            '//div[contains(concat(" ", normalize-space(@class), " "), " dropDownMenu ")]//input[contains(concat(" ", normalize-space(@class), " "), " dijitArrowButtonInner ")]',
        )
        self.selenium.click_element(
            '//*[contains(concat(" ", normalize-space(@class), " "), " dijitMenuItem ")][@role="option"]//*[contains(text(), "%s")]'
            % (category,),
        )
        sleep(2)

    def click_app_tile(self, app_name: str) -> None:
        self.selenium.click_element(expand_path(f'//*[@containsClass="umcTile__name"][text() = "{app_name}"]'))

    def open(self, do_reload: bool = True) -> None:
        # TODO: check if appcenter is already opened with the overview site
        self.selenium.open_module(_('App Center'), do_reload=do_reload, wait_for_standby=False)
        self.close_info_dialog_if_visisble()
        self.selenium.wait_until_standby_animation_appears_and_disappears()

    def open_app(self, app_name: str) -> None:
        # TODO: check if appcenter is already opened with the app page
        self.open()
        self.click_app_tile(app_name)
        self.selenium.wait_for_text(_('More information'))
        self.selenium.wait_until_all_standby_animations_disappeared()

    def close_info_dialog_if_visisble(self) -> None:
        try:
            self.selenium.wait_for_text(_('Do not show this message again'), timeout=5)
            self.selenium.click_button(_('Continue'))
        except TimeoutException:
            print('"Do not show this message again" not detected in 5 seconds')
        self.selenium.wait_until_all_standby_animations_disappeared()


if __name__ == '__main__':
    import univention.testing.selenium
    s = univention.testing.selenium.UMCSeleniumTest()
    s.__enter__()
    s.do_login()
    a = AppCenter(s)
    a.install_app('dudle')
    a.uninstall_app('dudle')
