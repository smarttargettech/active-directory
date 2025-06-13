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

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
from univention.admin import localization


if TYPE_CHECKING:
    from collections.abc import Mapping


translator = localization.translation('ucs-test-framework')
_ = translator.translate


class UDMBase:

    name = None

    def __init__(self, selenium: Any) -> None:
        self.selenium = selenium

    def _get_search_value(self, objectname: Any) -> str:
        return objectname

    def _get_grid_value(self, objectname: Any) -> str:
        return objectname

    def exists(self, objectname: str) -> bool:
        print('*** check if object exists', objectname)
        # This method will work with *most* UDM modules.
        self.search(self._get_search_value(objectname))
        time.sleep(5)
        self.selenium.wait_until_all_standby_animations_disappeared()
        try:
            self.selenium.wait_for_text(self._get_grid_value(objectname), timeout=1)
            return True
        except TimeoutException:
            pass
        return False

    def open_module(self):
        self.selenium.open_module(self.name)

    def open_details(self, objectname: str) -> None:
        print('*** open detail page of object', objectname)
        # This method will work with *most* UDM modules.
        self.search(self._get_search_value(objectname))
        self.selenium.click_grid_entry(self._get_grid_value(objectname))
        self.selenium.wait_until_standby_animation_appears_and_disappears()

    def close_details(self) -> None:
        print('*** close the detailpage')
        self.selenium.click_button(_('Back'))
        self.wait_for_main_grid_load()

    def save_details(self) -> None:
        print('*** save the detailpage')
        self.selenium.click_button(_('Save'))
        self.wait_for_main_grid_load()

    def delete(self, objectname: str) -> None:
        print('*** remove the object with name=', objectname)
        # This method will work with *most* UDM modules.
        self.search(self._get_search_value(objectname))

        self.selenium.click_checkbox_of_grid_entry(self._get_grid_value(objectname))
        self.selenium.click_button(_('Delete'))
        self.selenium.wait_for_text(_("Please confirm the removal"))
        self.selenium.click_element(
            '//div[contains(concat(" ", normalize-space(@class), " "), " dijitDialog ")]'
            '//*[contains(concat(" ", normalize-space(@class), " "), " dijitButtonText ")]'
            '[text() = "%s"]' % (_("Delete"),),
        )
        # FIXME: this waits forever and let's the test fail when no grid entries exists.
        # self.wait_for_main_grid_load()

    def search(self, objectname: str) -> None:
        print('*** searching for objects with name=', objectname)
        # This method will work with *most* UDM modules.
        xpath = '//input[@name="objectPropertyValue"]'
        elems = webdriver.support.ui.WebDriverWait(xpath, 60).until(
            self.selenium.get_all_enabled_elements,
        )
        elems[0].clear()
        elems[0].send_keys(objectname)
        elems[0].send_keys(Keys.RETURN)
        self.wait_for_main_grid_load()
        elems[0].clear()

    def wait_for_main_grid_load(self, timeout: int = 60) -> None:
        print('*** waiting for main grid load')
        self.selenium.wait_until_standby_animation_appears_and_disappears()

    def open_add_dialog(self, container: str | None = None, template: str | None = None) -> None:
        print('*** open the add dialog')
        self.selenium.click_button(_('Add'))
        self.selenium.wait_until_all_standby_animations_disappeared()

        try:
            self.selenium.wait_for_text(_('This UCS system is part of an Active Directory domain'), timeout=1)
        except TimeoutException:
            pass
        else:
            self.selenium.click_button(_('Next'))
            # FIXME: clicking Next on the page with the active directory warning
            # cuts the dialog in half and the dom elements are not clickable/visible.
            # This is a workaround
            dialogs = self.selenium.driver.find_elements(By.CLASS_NAME, 'umcUdmNewObjectDialog')
            if len(dialogs):
                self.selenium.driver.execute_script('dijit.byId("%s")._position()' % (dialogs[0].get_attribute('widgetid')))

        click_next = False
        try:
            self.selenium.wait_for_text(_('Container'), timeout=1)
            click_next = True
        except TimeoutException:
            pass

        # FIXME: select the given container

        try:
            self.selenium.wait_for_text(_("User template"), timeout=1)
            click_next = True
        except TimeoutException:
            pass

        if template is not None:
            self.selenium.enter_input_combobox('objectTemplate', template)

        if click_next:
            self.selenium.click_button(_('Next'))
            self.selenium.wait_until_all_standby_animations_disappeared()

    def open_advanced_add_dialog(self, **kwargs: Any) -> None:
        self.open_add_dialog(**kwargs)
        self.selenium.click_button(_('Advanced'))


class Portals(UDMBase):
    name = _('Portal settings')

    def __init__(self, selenium: Any) -> None:
        super().__init__(selenium)
        self.ucr = ucr_test.UCSTestConfigRegistry()
        self.ucr.load()

    def add(self, portalname: str | None = None, hostname: str | None = None) -> str:
        if portalname is None:
            portalname = uts.random_string()

        self.open_add_dialog()

        # FIXME: add this to the open_add_dialog() function
        self.selenium.enter_input_combobox('objectType', 'Portal: Portal')
        self.selenium.wait_until_standby_animation_appears_and_disappears()
        self.selenium.click_button('Next')

        self.selenium.wait_until_standby_animation_appears_and_disappears()
        self.selenium.enter_input("name", portalname)
        self.selenium.enter_input_combobox('__displayName-0-0', 'en_US', with_click=False)
        self.selenium.enter_input('__displayName-0-1', uts.random_string())

        if hostname is not None:
            self.selenium.enter_input_combobox('__portalComputers-0-0', hostname)

        self.selenium.click_button(_("Create portal"))
        self.wait_for_main_grid_load()

        return portalname


class Computers(UDMBase):
    name = _('Computers')

    def add(self, computername: str | None = None) -> str:
        if computername is None:
            computername = uts.random_string()

        self.open_add_dialog()
        self.selenium.enter_input("name", computername)
        self.selenium.click_button(_("Create computer"))
        self.selenium.wait_for_text(_('has been created'))
        self.selenium.click_button(_('Cancel'))
        self.selenium.wait_until_all_dialogues_closed()

        return computername


class Groups(UDMBase):
    name = _("Groups")

    def add(self, groupname: str | None = None) -> str:
        if groupname is None:
            groupname = uts.random_string()

        self.open_add_dialog()
        self.selenium.wait_for_text(_("Members of this group"))
        self.selenium.enter_input("name", groupname)
        self.selenium.click_button(_("Create group"))
        self.wait_for_main_grid_load()

        return groupname


class Policies(UDMBase):
    name = _('Policies')

    def add(self, policyname: str | None = None) -> str:
        if policyname is None:
            policyname = uts.random_string()

        self.open_add_dialog()
        self.selenium.enter_input("name", policyname)
        self.selenium.click_button(_("Create policy"))
        self.wait_for_main_grid_load()

        return policyname

    # fails in 4.4-0, Bug #48998
    # def open_details(self, objectname):
    #     self.search(self._get_search_value(objectname))
    #     self.selenium.click_grid_entry(self._get_grid_value(objectname))
    #     self.selenium.wait_for_text(_('Advanced settings'))


class Users(UDMBase):
    name = _("Users")

    def __init__(self, selenium: Any) -> None:
        super().__init__(selenium)
        self.ucr = ucr_test.UCSTestConfigRegistry()
        self.ucr.load()

    def get_description(self) -> str:
        xpath = '//input[@name="description"]'
        elems = webdriver.support.ui.WebDriverWait(xpath, 60).until(
            self.selenium.get_all_enabled_elements,
        )
        return elems[0].get_attribute('value')

    def get_primary_mail(self) -> str:
        xpath = '//input[@name="mailPrimaryAddress"]'
        elems = webdriver.support.ui.WebDriverWait(xpath, 60).until(
            self.selenium.get_all_enabled_elements,
        )
        return elems[0].get_attribute('value')

    def add(
            self,
            template: str | None = None,
            firstname: str = '',
            lastname: str | None = None,
            username: str | None = None,
            password: str = 'univention',
    ) -> dict[str, str]:
        if username is None:
            username = uts.random_string()
        if lastname is None:
            lastname = uts.random_string()

        self.open_add_dialog(template=template)

        self.selenium.wait_for_text(_("First name"))
        self.selenium.enter_input("firstname", firstname)
        self.selenium.enter_input("lastname", lastname)
        self.selenium.enter_input("username", username)

        self.selenium.click_button(_("Next"))
        self.selenium.wait_for_text(_("Password"))
        self.selenium.enter_input("password_1", password)
        self.selenium.enter_input("password_2", password)
        self.selenium.click_button(_("Create user"))
        self.selenium.wait_for_text(_('has been created'))
        self.selenium.click_button(_('Cancel'))
        self.selenium.wait_until_all_dialogues_closed()

        return {'username': username, 'lastname': lastname}

    def copy(self, user, username='', lastname='', password='univention', **kwargs):
        username = username or uts.random_string()
        self.search(user)
        self.selenium.click_checkbox_of_grid_entry(user)
        self.selenium.click_text(_('more'))
        self.selenium.click_text(_('Copy'))
        try:
            self.selenium.wait_for_any_text_in_list(['Container', 'Template'], timeout=5)
            self.selenium.click_button('Next')
        except TimeoutException:
            pass
        finally:
            self.selenium.wait_until_standby_animation_appears_and_disappears()

        self.selenium.enter_input('username', username)
        self.selenium.enter_input('lastname', lastname or uts.random_string())
        self.selenium.enter_input('password_1', password)
        self.selenium.enter_input('password_2', password)
        for key, value in kwargs.items():
            self.selenium.enter_input(key, value)
        self.selenium.click_text(_('Create user'))
        self.selenium.wait_until_standby_animation_appears_and_disappears()
        # TODO: check for error
        return username

    def _get_search_value(self, user: Mapping[str, str]) -> str:
        return user['username']

    def _get_grid_value(self, user: Mapping[str, str]) -> str:
        return user['lastname'] if self.ucr.get('ad/member') else user['username']
