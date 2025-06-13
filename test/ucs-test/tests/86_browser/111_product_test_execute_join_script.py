#!/usr/share/ucs-test/runner /usr/share/ucs-test/selenium
## desc: Execute a custom join script.
## packages:
##  - univention-management-console-module-join
## roles-not:
##  - basesystem
## tags:
##  - skip_admember
##  - SKIP
## join: true
## exposure: dangerous

import os
import time
from shutil import copyfile

from selenium import webdriver
from selenium.common.exceptions import TimeoutException

from univention.lib.i18n import Translation
from univention.testing import selenium


_ = Translation('ucs-test-selenium').translate


class PasswordChangeError(Exception):
    pass


class UMCTester:

    def test_umc(self):
        try:
            self.save_status_file()
            self.add_test_join_script()
            self.selenium.do_login()
            self.open_join_module()

            joinscript = '99univention-test-join-script'
            self.assert_joinscript_status(joinscript, 'pending')
            self.run_join_script(joinscript)
            self.selenium.do_login()
            self.open_join_module()
            self.assert_joinscript_status(joinscript, 'successful')

            # TODO: Also test 'Force execute'.
            # TODO: Also test 'Execute all pending join scripts' with multiple pending scripts.
        finally:
            self.remove_test_join_script()
            self.restore_status_file()

    def save_status_file(self):
        copyfile('/var/univention-join/status', '/var/univention-join/status.bak')

    def restore_status_file(self):
        os.rename('/var/univention-join/status.bak', '/var/univention-join/status')

    def add_test_join_script(self):
        copyfile('/usr/share/ucs-test/60_umc/99univention_test_join_script.inst', '/usr/lib/univention-install/99univention-test-join-script.inst')
        os.chmod('/usr/lib/univention-install/99univention-test-join-script.inst', 0o755)

    def remove_test_join_script(self):
        if os.path.exists('/usr/lib/univention-install/99univention-test-join-script.inst'):
            os.unlink('/usr/lib/univention-install/99univention-test-join-script.inst')

    def open_join_module(self):
        self.selenium.open_module(_('Domain join'))
        xpaths = ['//div[contains(concat(" ", normalize-space(@class), " "), " dgrid-row ")]']
        webdriver.support.ui.WebDriverWait(xpaths, 60).until(
            self.selenium.get_all_visible_elements, 'Waited 60s for grid load.',
        )
        self.selenium.wait_for_text('99univention-test-join-script')
        self.selenium.wait_until_all_standby_animations_disappeared()

    def run_join_script(self, joinscript):
        self.scroll_join_script_into_view(joinscript)
        self.selenium.click_grid_entry(joinscript)
        self.selenium.click_button(_('Execute'))

        try:
            self.selenium.wait_for_text(_('Please enter credentials'), timeout=2)
        except TimeoutException:
            self.selenium.click_button(_('Run join scripts'))
        else:
            self.selenium.enter_input('username', self.selenium.umcLoginUsername)
            self.selenium.enter_input('password', self.selenium.umcLoginPassword)
            self.selenium.click_button(_('Run'))

        self.selenium.wait_until_all_standby_animations_disappeared()
        self.selenium.wait_for_text(_('restart of the UMC server'), timeout=60)
        self.selenium.click_button(_('Restart'))
        self.selenium.wait_until_all_standby_animations_disappeared()

        time.sleep(15)

    def assert_joinscript_status(self, joinscript, status):
        test_state = self.get_joinscript_status(joinscript)
        assert status == test_state, 'The state of the script %s is %r instead of %r' % (joinscript, test_state, status)

    def get_joinscript_status(self, joinscript):
        self.scroll_join_script_into_view(joinscript)
        xpath = '//*[contains(concat(" ", normalize-space(@class), " "), " dgrid-cell ")][@role="gridcell"]/descendant-or-self::node()[contains(text(), "%s")]/../*[contains(concat(" ", normalize-space(@class), " "), " field-status ")]/*' % (joinscript,)
        elems = webdriver.support.ui.WebDriverWait(xpath, 60).until(
            self.selenium.get_all_enabled_elements,
        )
        return elems[0].get_attribute('innerHTML')

    def scroll_join_script_into_view(self, joinscript):
        xpath = '//*[contains(concat(" ", normalize-space(@class), " "), " dgrid-cell ")][@role="gridcell"]/descendant-or-self::node()[contains(text(), "%s")]' % (joinscript,)
        elems = webdriver.support.ui.WebDriverWait(xpath, 60).until(
            self.selenium.get_all_enabled_elements,
        )
        self.selenium.driver.execute_script("arguments[0].scrollIntoView();", elems[0])


if __name__ == '__main__':
    with selenium.UMCSeleniumTest() as s:
        umc_tester = UMCTester()
        umc_tester.selenium = s

        umc_tester.test_umc()
