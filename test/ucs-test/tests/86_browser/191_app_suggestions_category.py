#!/usr/share/ucs-test/runner /usr/share/ucs-test/playwright
## desc: |
##  Test that suggestions category is shown
## roles-not:
##  - basesystem
## tags:
##  - skip_admember
## join: true
## exposure: dangerous

from playwright.sync_api import expect

from univention.testing.browser.appcenter import AppCenter
from univention.testing.browser.lib import UMCBrowserTest
from univention.testing.browser.suggestion import AppCenterCacheTest
from univention.testing.utils import package_installed


def test_suggestion_category_is_shown(umc_browser_test: UMCBrowserTest, app_center_cache: AppCenterCacheTest):
    app_center_cache.write(
        """
{
    "v1": [{
        "condition": [],
        "candidates": [{
            "id": "pkgdb",
            "mayNotBeInstalled": []
        }]
    }]
}
""",
    )
    if package_installed('univention-pkgdb'):
        return
    app_center = AppCenter(umc_browser_test)
    app_center.navigate()

    expected_text = umc_browser_test.page.get_by_text('Suggestions based on installed apps')
    expect(expected_text).to_be_visible(timeout=10 * 1000)
    umc_browser_test.page.screenshot(path=__name__)
