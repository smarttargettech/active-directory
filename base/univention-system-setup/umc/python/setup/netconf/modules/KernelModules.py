#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# SPDX-FileCopyrightText: 2024-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only


from univention.management.console.modules.setup.netconf.common import Executable


class PhaseKernelModules(Executable):
    """(Un-)load kernel modules for VLAN, Bridging, Bonding."""

    variable_name = "kernel/modules"
    variable_separator = ";"
    module_option = (
        ("8021q", "vlan-raw-device"),
        ("bridge", "bridge_ports"),
        ("bonding", "bond-slaves"),
    )
    priority = 95
    executable = "/sbin/modprobe"

    def pre(self) -> None:
        modules = self.get_configured_modules()
        self.clean_known_modules(modules)
        new_modules = self.scan_required_modules()
        modules |= new_modules
        self.set_configured_modules(modules)
        self.load_modules(new_modules)

    def get_configured_modules(self) -> set[str]:
        value = self.changeset.ucr.get(self.variable_name, "")
        modules = set(value.split(self.variable_separator))
        modules.discard("")
        return modules

    def clean_known_modules(self, modules: set[str]) -> None:
        modules.difference_update(module for module, _option in self.module_option)

    def scan_required_modules(self) -> set[str]:
        modules = set()
        for _name, iface in self.changeset.new_interfaces.all_interfaces:
            for iface_option in iface.options:
                for module, option in self.module_option:
                    if iface_option.startswith(option):
                        modules.add(module)
        return modules

    def set_configured_modules(self, modules: set[str]) -> None:
        value = self.variable_separator.join(sorted(modules)) or None
        self.logger.info("Updating '%s'='%s'...", self.variable_name, value)
        self.changeset.ucr_changes[self.variable_name] = value

    def load_modules(self, modules: set[str]) -> None:
        if modules:
            cmd = [self.executable, *list(modules)]
            self.call(cmd)
