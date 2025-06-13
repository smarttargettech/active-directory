#!/usr/share/ucs-test/runner python3
## desc: Screenshot script for the Users module
## roles-not: [basesystem]
## exposure: dangerous

from lib.screen_shooter import BaseScreenShooter
from selenium.webdriver.common.by import By

from univention.admin import localization


translator = localization.translation('univention-ucs-test_umc-screenshots')
_ = translator.translate


class ScreenShooter(BaseScreenShooter):
    def take_screenshots(self):
        self.open_module_and_take_overview_screenshot()
        self.take_screenshots_of_adding_a_user()
        self.take_screenshot_of_details_page()

    def open_module_and_take_overview_screenshot(self):
        self.selenium.open_module(_('Users'))
        self.selenium.wait_for_text(":/users")
        self.selenium.wait_until_all_standby_animations_disappeared()
        self.selenium.save_screenshot("umc-users")

    def take_screenshots_of_adding_a_user(self):
        self.selenium.click_button(_("Add"))
        self.take_template_screenshot_and_move_on()
        self.selenium.wait_for_text(_("First name"))
        self.selenium.enter_input("firstname", "Anna")
        self.selenium.enter_input("lastname", "Alster")
        self.selenium.enter_input("username", "anna")
        self.selenium.save_screenshot(
            "umc-users-add_dialog",
            xpath='//*[contains(concat(" ", normalize-space(@class), " "), " umcUdmNewObjectDialog ")]',
        )
        # self.selenium.click_button(_("Next"))
        # self.selenium.wait_for_text(_("Password *"))
        # self.selenium.enter_input("password_1", "univention")
        # self.selenium.enter_input("password_2", "univention")
        self.selenium.click_button(_("Cancel"))
        self.selenium.wait_until_all_dialogues_closed()

    def take_template_screenshot_and_move_on(self):
        self.selenium.wait_for_text(_("User template"))
        template_selection_dropdown_button = self.selenium.driver.find_element(
            By.XPATH,
            '//input[@name="objectTemplate"]/../..//input[contains(concat(" ", normalize-space(@class), " "), " dijitArrowButtonInner ")]',
        )
        template_selection_dropdown_button.click()
        self.selenium.save_screenshot(
            "umc-users-template",
            xpath='//*[contains(concat(" ", normalize-space(@class), " "), " umcUdmNewObjectDialog ")]',
        )
        template_selection_dropdown_button.click()
        self.selenium.click_button(_("Next"))

    def take_screenshot_of_details_page(self):
        self.selenium.click_grid_entry("anna")
        self.selenium.wait_for_text(_("password history"))
        self.selenium.wait_until_all_standby_animations_disappeared()
        self.selenium.save_screenshot("umc-users-details")


# This is a base64 encoded jpeg image of an user portrait.
portraitPhoto = """
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
"""

if __name__ == '__main__':
    with ScreenShooter(translator) as screen_shooter:
        screen_shooter.udm.create_user(username='anna', firstname='Anna', lastname='Alster', jpegPhoto=portraitPhoto)
        screen_shooter.udm.create_object(
            'settings/usertemplate', name=_('Developer'),
            position=f"cn=templates,cn=univention,{screen_shooter.selenium.ldap_base}",
        )
        screen_shooter.udm.create_object(
            'settings/usertemplate', name=_('Guest'),
            position=f"cn=templates,cn=univention,{screen_shooter.selenium.ldap_base}",
        )

        screen_shooter.take_screenshots()
