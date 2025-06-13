#!/usr/share/ucs-test/runner python3
## desc: packages held back
## tags: [apptest]
## bugs: [14610]
## exposure: safe

import apt_pkg

from univention.testing import utils


def get_heldback_pkgs():
    """
    Returns a list of apt_pkg.Package.name list\n
    type = list of str
    """
    held_pkgs = []
    apt_pkg.init_config()
    apt_pkg.init_system()
    cache = apt_pkg.Cache()
    for pkg in cache.packages:
        if pkg.selected_state == apt_pkg.SELSTATE_HOLD:
            held_pkgs.append(pkg.name)
    return held_pkgs


if __name__ == '__main__':
    heldback_pkgs = get_heldback_pkgs()
    if heldback_pkgs:
        utils.fail('Packages held back: %r' % heldback_pkgs)
