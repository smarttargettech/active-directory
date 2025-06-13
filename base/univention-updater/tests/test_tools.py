#!/usr/bin/python3
# pylint: disable-msg=C0301,W0212,C0103,R0904
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# SPDX-FileCopyrightText: 2024-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""Unit test for univention.updater.tools"""

import univention.updater.tools as U


SCRIPT = b"#!/bin/sh\nexit 0\n"
SIGNATURE = b"""\
-----BEGIN PGP SIGNATURE-----

iQIcBAABCAAGBQJe9HpqAAoJEDZgK6hri/08ft0P/iVmAsf6J4qF2MHx80Xy0Zgw
fq313ZUZsJ1FAAB1U8fdqiY6EGaHcLHO+xpjY2tPNrefKJd+hpIJFTGa6dvdj3Ab
H4LlukVvzNdCWsT24ogz+pgFFyav8+uq8mRwxLPlvRRi+2Ui0mGaXBXhxsgrCM94
6JvjfQatjKl+5eIwnsn/eHMke1NyWUoL73LGv0zSGNqIKnAjei9ae/dpOQecZqQR
e5uk0W/71vbZeSGDt9gfseHXds2kXMaQzL9+ztB6j22Lgiy6R8zidXXI5XtywgzI
wt6K45W880r0LIFI0V4z9jKXet12imx0r6m67dkDCubrzt0BEJRX8LcPBuoit4Q2
Z+xqHVtwyPni6/gBZCdwtvwp5mk0ge6zzsQT2Ez8epFqyy5xCfnO3tuNq60d2MX5
qbKe1LQp+wQu2LDQl3EMBS/WZN2ftuQvrKj4UnFV5dqo4qdpvIshaYy1WBSyojtB
MVmdk7w/i78uwAoOqGWixza4MJdqg4nykUX3SUsPdZ04LKabIz+XgqNmPsfgO5oH
RGpatng+HRtEgJ/HKLR4O0YQH1U9eI63Sk4HqzZ+sFIhd7eS9LTRD5R+veLJ2/5t
tukVccC7cD1Zp4zz5+AgCLFpvBSa7h0IzdAnjt0F0eu2iYRPEwHycJbgRH66hkpi
erp3pQbx5rD0cMYJBw3K
=TWKR
-----END PGP SIGNATURE-----
"""


class TestSignatures:
    def test_verify_script(self):
        assert U.verify_script(SCRIPT, SIGNATURE) is None
