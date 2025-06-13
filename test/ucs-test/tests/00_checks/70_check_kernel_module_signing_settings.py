#!/usr/share/ucs-test/runner python3
## desc: check for the correct settings for signed kernel modules
## exposure: safe
## bugs: [36383]
## versions:
##  4.3-0: skip

from os import uname

from univention.testing import utils


MINIMUM_CONFIG = [
    "CONFIG_MODULE_SIG=y",
    "CONFIG_MODULE_SIG_SHA512=y",
    'CONFIG_MODULE_SIG_HASH="sha512"',
    "CONFIG_MODULE_SIG_ALL=y",
    "# CONFIG_MODULE_SIG_FORCE is not set",
]


def main():

    # determine the kernel release name, to get the name of the config-file
    # file name is /boot/config-$(uname -r)
    (_sysname, _nodename, release, _version, _machine) = uname()
    config_file = f"/boot/config-{release}"

    # check if all lines that appear in the above MINIMUM_CONFIG are also
    # set in the config file.

    missing_config_lines = set(MINIMUM_CONFIG)
    with open(config_file) as cfg:
        missing_config_lines.difference_update(line.strip() for line in cfg)

    if missing_config_lines:
        msg = "The following lines are missing in {}:\n {}".format(
            config_file,
            '\n '.join(missing_config_lines),
        )
        utils.fail(msg)


if __name__ == "__main__":
    main()
