#!/usr/share/ucs-test/runner python3
## desc: Test password change via UMC (/univention/set) by the user itself.
## bugs: [35276, 36900]
## roles: [domaincontroller_master]
## packages:
##  - univention-directory-manager-tools
## tags: [basic, apptest, skip_admember]
## exposure: dangerous

from time import sleep

import pytest

import univention.testing.strings as uts
from univention.config_registry import ConfigRegistry
from univention.lib.umc import BadRequest
from univention.testing import utils
from univention.testing.udm import UCSTestUDM, UCSTestUDM_CreateUDMObjectFailed
from univention.testing.umc import Client


def main():
    """
    Creates a container in LDAP;
    Creates a test user inside it;
    Tries to change user's password to a new (complex) one;
    Tries to change user's password to a new (simple) one;
    Removes the test user and container.
    """
    ucr = ConfigRegistry()
    ucr.load()

    with UCSTestUDM() as udm:
        # create an ldap container:
        try:
            container = udm.create_object('container/cn', position=ucr.get('ldap/base'), name='ucs_test_' + uts.random_string())
        except UCSTestUDM_CreateUDMObjectFailed:
            print('udm.create_object failed, wait for 30 seconds and try again ...')
            sleep(30)
            container = udm.create_object('container/cn', position=ucr.get('ldap/base'), name='ucs_test_' + uts.random_string())

        # create a test user inside container:
        user_name = 'ucs_test_' + uts.random_string()
        user_password = uts.random_string()
        user_kwargs = {
            'position': container,
            'lastname': user_name,
            'password': user_password,
            'username': user_name,
        }

        print("\nCreating a user for the test:")
        udm.create_user('users/user', **user_kwargs)
        sleep(10)  # wait a bit before trying to authenticate

        # generate new user passwords (complex and simple ones):
        complex_password = 'Foo1_' + uts.random_string() + '_Bar2'
        simple_password = 'foo'

        # try to authenticate and change password of the user
        # to the 'complex' one (should work):
        print("\nTrying to change user password to '%s':" % complex_password)
        client = Client(None, user_name, user_password)
        response = client.umc_set({'password': {'password': user_password, 'new_password': complex_password}})
        print("RESPONSE:", response)
        if response.status != 200:
            utils.fail("Changing user password did not work in the case it should")

        # try to authenticate with a new user password
        # and change it to a simple one (should not work):
        print("\nTrying to change user password to '%s':" % simple_password)
        client = Client(None, user_name, complex_password)
        with pytest.raises(BadRequest):
            response = client.umc_set({'password': {'password': complex_password, 'new_password': simple_password}})
            print("RESPONSE:", response)
            if response.status == 200:
                utils.fail("Changing user password worked in the case it should not")


if __name__ == '__main__':
    main()
