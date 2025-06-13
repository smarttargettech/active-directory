#!/usr/share/ucs-test/runner python3
## desc: Check UCR handlers getting registered only once
## roles: [domaincontroller_master, domaincontroller_backup]
## packages:
##  - univention-base-files
## exposure: dangerous

import pickle  # noqa: S403
import sys

import univention.config_registry.handler as ucrh
from univention.config_registry.frontend import handler_register
from univention.testing import utils


UCR_CACHE = '/var/cache/univention-config/cache'

print('Re-registering package univention-base-files...')
handler_register(['univention-base-files'])

with open(UCR_CACHE, "rb") as f:
    f.readline()
    d = pickle.load(f, encoding='bytes')

modules = []

print('Check if UCR variable xorg/keyboard/options/XkbModel has more than one module attached...')
value = d['xorg/keyboard/options/XkbModel']
for val in value:
    if isinstance(val, ucrh.ConfigHandlerModule):
        modules.append(val.module)

if len(modules) > 1:
    utils.fail('Error: module %s was registered more than once' % modules[0])
    sys.exit(1)

# vim: ft=python
