#!/usr/share/ucs-test/runner python3
## desc: Ignore odering of multi-valued attributes during modify
## tags:
##  - apptest
##  - SKIP-UCSSCHOOL
## roles-not:
##  - basesystem
## packages:
##  - python3-univention-lib
## exposure: careful
## bugs:
##  - 40120
##  - 40602

from univention.testing.strings import random_name
from univention.testing.udm import UCSTestUDM
from univention.uldap import getMachineConnection


ATTR = 'prohibitedUsername'
container_name = random_name()
names = ['%s%d' % (random_name(), i) for i in range(2)]

with UCSTestUDM() as udm:
    dn = udm.create_object(
        'settings/prohibited_username',
        position=udm.UNIVENTION_CONTAINER,
        name=container_name,
        usernames=names,
    )

    access = getMachineConnection(ldap_master=True)
    result = access.search(base=dn, scope='base', attr=[ATTR])
    ((dn2, values),) = result
    assert dn == dn2
    old = values[ATTR]
    new = list(reversed(old))
    change = (ATTR, old, new)
    changes = [change]
    access.modify(dn, changes)

# vim: set ft=python :
