#!/usr/share/ucs-test/runner python3
## desc: Test UMC policy result
## bugs: [32271]
## roles:
##  - domaincontroller_master
## tags:
##  - SKIP
## packages:
##  - univention-management-console-module-udm
## exposure: careful

from univention.testing.strings import random_name
from univention.testing.udm import UCSTestUDM
from univention.testing.umc import Client
from univention.testing.utils import fail


USERNAME = None
PASSWORD = 'univention'

client = None


def get_policy_result_new(container=None, policyDN=None):
    return get_policy_result(None, policyDN, container)


def get_policy_result_edit(objectDN=None, policyDN=None):
    return get_policy_result(objectDN, policyDN, None)


def logged_in(func):
    def _decorated(*args, **kwargs):
        global client
        if client is None:
            client = Client(None, USERNAME, PASSWORD)
        return func(*args, **kwargs)
    return _decorated


@logged_in
def get_policy_result(objectDN, policyDN, container):
    """Gets the policy result from UMC"""
    data = [{
            'objectType': 'computers/domaincontroller_slave',
            'policies': [policyDN],
            'policyType': 'policies/registry',
            'objectDN': objectDN,
            'container': container,
            }]

    result = client.umc_command('udm/object/policies', data, 'navigation').result
    return ['='.join(r['value']) for r in result[0]['registry']]


def main():
    with UCSTestUDM() as udm:
        # create an UMC operation set to allow the udm/object/policies command
        operation_set_dn = udm.create_object(
            'settings/umc_operationset',
            position="cn=operations,cn=UMC,cn=univention,%s" % udm.LDAP_BASE,
            name='test-umc-opset',
            description="policy result test op set",
            operation=["udm/object/policies"],
            flavor='navigation',
        )

        # create a new UMC policy
        # containing the UMC operating set
        umc_policy_dn = udm.create_object(
            'policies/umc',
            position="cn=UMC,cn=policies,%s" % udm.LDAP_BASE,
            name='test-umc-policy',
            allow=operation_set_dn,
        )

        # create user to authenticate with at UMC
        # appending the created UMC policy
        global USERNAME
        _userdn, USERNAME = udm.create_user(**{  # noqa: PIE804
            'policy_reference': umc_policy_dn,
        })

        # create empty policies
        policies = {
            'root': {"registry": 'foo 1'},
            'container': {"registry": 'baz 2'},
            'computer': {"append": {"registry": ['baz 3', 'bar 4']}},
            'various': {"append": {"registry": ['foo 0', 'bar 5']}},
        }
        for name, kwargs in policies.items():
            policies[name] = udm.create_object(
                'policies/registry',
                position="cn=policies,%s" % udm.LDAP_BASE,
                name='test-%s-ucr-policy' % name,
                **kwargs,
            )

        # create container hierarchy
        root_dn = udm.create_object(
            'container/cn',
            name='root',
            position=udm.LDAP_BASE,
        )
        container_dn = udm.create_object(
            'container/cn',
            name='computers2',
            position=root_dn,
        )

        # create computer object
        computer_dn = udm.create_object(
            'computers/domaincontroller_slave',
            name=random_name(),
            position=container_dn,
        )

        root_policy_dn = policies['root']
        computer_policy_dn = policies['computer']
        container_policy_dn = policies['container']
        various_policy_dn = policies['various']

        # (1)
        #   [edit] editing an existing UDM object
        #   -> the existing UDM object itself is loaded
        #   [new]  virtually edit non-existing (=new) UDM object
        #   -> the parent container UDM object is loaded
        # (2)
        #   [w/pol]   UDM object has assigned policies in LDAP directory
        #   [w/o_pol] UDM object has no policies assigned in LDAP directory
        # (3)
        #   [inherit] user request to (virtually) change the policy to 'inherited'
        #   [set_pol] user request to (virtually) assign a particular policy

        #
        # creation tests
        #

        # assign policy to root container
        udm.modify_object('container/cn', **{  # noqa: PIE804
            'dn': root_dn,
            'policy_reference': root_policy_dn,
        })

        _assert(
            ["foo=1"],
            get_policy_result_new(container_dn),
            'new inherit w/o_pol',
        )
        _assert(
            ["foo=1", "baz=3", "bar=4"],
            get_policy_result_new(container_dn, computer_policy_dn),
            'new set_pol w/o_pol',
        )

        # assign policy to computer container
        udm.modify_object('container/cn', **{  # noqa: PIE804
            'dn': container_dn,
            'policy_reference': container_policy_dn,
        })

        _assert(
            ["foo=1", "baz=2"],
            get_policy_result_new(container_dn),
            'new inherit w/pol',
        )
        _assert(
            ["foo=1", "bar=4", "baz=3"],
            get_policy_result_new(container_dn, computer_policy_dn),
            'new set_pol w/pol',
        )

        #
        # modification tests
        #
        _assert(
            ["foo=1", "baz=2"],
            get_policy_result_edit(computer_dn),
            'edit inherit w/o_pol',
        )
        _assert(
            ["foo=1", "bar=4", "baz=3"],
            get_policy_result_edit(computer_dn, computer_policy_dn),
            'edit set_pol w/o_pol',
        )

        # assign policy to computer
        udm.modify_object('computers/domaincontroller_slave', **{  # noqa: PIE804
            'dn': computer_dn,
            'policy_reference': computer_policy_dn,
        })

        _assert(
            ["foo=1", "baz=2"],
            get_policy_result_edit(computer_dn),
            'edit inherit w/pol',
        )
        _assert(  # test with the same policy the object has assigned
            ["foo=1", "bar=4", "baz=3"],
            get_policy_result_edit(computer_dn, computer_policy_dn),
            'edit set_pol w/pol',
        )
        _assert(
            ["foo=0", "bar=5", "baz=2"],
            get_policy_result_edit(computer_dn, various_policy_dn),
            'edit set_pol w/pol (2)',
        )


def _assert(first, second, name):
    if set(first) != set(second):
        fail(f'ERROR: {name}: {set(first)!r} != {set(second)!r}')
    else:
        print('OK: %s' % name)


if __name__ == '__main__':
    main()
