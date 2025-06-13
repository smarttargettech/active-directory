#!/usr/share/ucs-test/runner pytest-3 -s -l -vvv
## desc: Test handling of non matching cert and private key with umc as SP
## tags: [saml]
## bugs: [47700]
## join: true
## roles: [domaincontroller_master]
## exposure: dangerous
## tags:
##  - skip_admember

import sys

from univention.testing import utils

import samltest


def test_umc_wrong_cert():
    with open('/etc/univention/ssl/ucsCA/CAcert.pem', 'rb') as ca_file:
        cert = ca_file.read()
    with samltest.SPCertificate(cert, update_metadata=False):
        umc_cert_fail()


def umc_cert_fail():
    sys.path.append("/usr/share/univention-management-console/saml/")
    try:
        import sp  # noqa: F401
    except BaseException as exc:
        #  Importing the exception would fail as well
        print(type(exc).__name__)
        if type(exc).__name__ == "CertDoesNotMatchPrivateKeyError":
            print("OK: UMC throws an error for mismatch in cert and private key")
        else:
            raise
    else:
        utils.fail("UMC accepted mismatching cert")
