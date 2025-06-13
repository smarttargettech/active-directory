#!/usr/share/ucs-test/runner /usr/share/ucs-test/selenium
## desc: Test changing Appearance CSS background from within the portal
## roles:
##  - domaincontroller_master
## tags:
##  - SKIP
##  - skip_admember
## join: true
## exposure: dangerous

import logging
import time

from selenium.webdriver.common.by import By

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
from univention.lib.i18n import Translation
from univention.testing import selenium
from univention.testing.udm import UCSTestUDM
from univention.udm import UDM


logger = logging.getLogger(__name__)

_ = Translation('ucs-test-selenium').translate


class ChangeBackgroundCSSError(Exception):
    pass


class UMCTester:

    def test_umc(self):
        try:
            self.init()
            self.do_test()
        finally:
            self.cleanup()

    def init(self):
        logger.info('Creating dummy portal')
        self.dummy_portal_title = uts.random_string()
        self.dummy_portal_dn = self.udm_test.create_object(
            'settings/portal',  # TODO: migrate to new portal
            name=uts.random_string(),
            displayName=['en_US ' + self.dummy_portal_title],
        )
        logger.info('Saving previous set portal of host')
        udm = UDM.admin().version(1)
        machine = udm.obj_by_dn(self.ucr['ldap/hostdn'])
        self.previous_portal = machine.props.portal
        logger.info('Setting dummy portal as portal for host')
        machine.props.portal = self.dummy_portal_dn
        machine.save()

    def do_test(self):
        self.selenium.do_login()

        logger.info('Visiting dummy portal')
        self.selenium.driver.get(self.selenium.base_url)
        self.selenium.wait_for_text(self.dummy_portal_title)

        logger.info('Check if inline edit is active')
        self.selenium.wait_until_element_visible('//div[@class="portalEditFloatingButton"]')
        logger.info('Enter edit mode')
        self.selenium.click_element('//div[@class="portalEditFloatingButton"]')
        time.sleep(2)  # css transition

        logger.info('Setting new CSS background')
        self.selenium.click_button('Appearance')
        self.selenium.enter_input('cssBackground', 'rgba(100, 100, 100, 1);')
        self.selenium.click_button('Save')
        self.selenium.wait_until_all_dialogues_closed()

        logger.info('Waiting for css to be reloaded')
        time.sleep(10)  # wait for the css to be reloaded

        logger.info('Checking whether changing the background css worked')
        body_background = self.selenium.driver.find_element(By.TAG_NAME, 'body').value_of_css_property('background')
        if 'rgb(100, 100, 100)' not in body_background:
            # the appearance changes should be hot reloaded so this is a fail
            # but check if the color was changed at all

            logger.info('Visiting dummy portal')
            self.selenium.driver.get(self.selenium.base_url)
            self.selenium.wait_for_text(self.dummy_portal_title)

            body_background = self.selenium.driver.find_element(By.TAG_NAME, 'body').value_of_css_property('background')
            if 'rgb(100, 100, 100)' not in body_background:
                raise ChangeBackgroundCSSError('Changing the background css did not work')
            raise ChangeBackgroundCSSError('(Setting) The background css should be hot reloaded after a save but it was not')

    def cleanup(self):
        logger.info('Cleanup')
        if hasattr(self, 'previous_portal'):
            logger.info('Restore previously set portal on host')
            udm = UDM.admin().version(1)
            machine = udm.obj_by_dn(self.ucr['ldap/hostdn'])
            machine.props.portal = self.previous_portal
            machine.save()


if __name__ == '__main__':
    with ucr_test.UCSTestConfigRegistry() as ucr, UCSTestUDM() as udm_test, selenium.UMCSeleniumTest() as s:
        umc_tester = UMCTester()
        umc_tester.ucr = ucr
        umc_tester.udm_test = udm_test
        umc_tester.selenium = s

        umc_tester.test_umc()
