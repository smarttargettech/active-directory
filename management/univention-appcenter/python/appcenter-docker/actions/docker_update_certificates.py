#!/usr/bin/python3
#
# Univention App Center
#  univention-app module for configuring an app
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2015-2025 Univention GmbH
#
# https://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <https://www.gnu.org/licenses/>.

import os

from univention.appcenter.actions.docker_base import DockerActionMixin
from univention.appcenter.actions.update_certificates import UpdateCertificates
from univention.appcenter.ucr import ucr_get


class UpdateCertificates(UpdateCertificates, DockerActionMixin):

    def _copy_host_cert(self, docker, host_ssl_dir, dest):
        docker.execute('mkdir', '-p', dest, _logger=self.logfile_logger)
        docker.execute('chmod', '750', dest, _logger=self.logfile_logger)
        docker.cp_to_container(f'{host_ssl_dir}/cert.pem', f'{dest}/cert.perm', _logger=self.logfile_logger)
        docker.cp_to_container(f'{host_ssl_dir}/private.key', f'{dest}/private.key', _logger=self.logfile_logger)

    def update_certificates(self, app):
        hostname = ucr_get('hostname')
        domain = ucr_get('domainname')
        docker_host_cert = '/etc/univention/ssl/' + hostname + '.' + domain
        if app.docker:
            docker = self._get_docker(app)
            if docker.is_running():
                ca_path = '/etc/univention/ssl/ucsCA/CAcert.pem'
                if os.path.isfile(ca_path):
                    # update-ca-certificates, debian, ubuntu, appbox
                    docker.execute('mkdir', '-p', '/usr/local/share/ca-certificates', _logger=self.logfile_logger)
                    docker.cp_to_container(ca_path, '/usr/local/share/ca-certificates/ucs.crt', _logger=self.logfile_logger)
                    if docker.execute('which', 'update-ca-certificates', _logger=self.logfile_logger).returncode == 0:
                        docker.execute('update-ca-certificates', _logger=self.logfile_logger)
                    # appboox ca cert
                    docker.execute('mkdir', '-p', '/etc/univention/ssl/ucsCA/', _logger=self.logfile_logger)
                    docker.cp_to_container(ca_path, ca_path, _logger=self.logfile_logger)
                # docker host cert canonical name and ucs path
                if os.path.isfile(f'{docker_host_cert}/cert.pem') and os.path.isfile(f'{docker_host_cert}/private.key'):
                    # canonical name
                    self._copy_host_cert(docker, docker_host_cert, '/etc/univention/ssl/docker-host-certificate')
                    # ucs name
                    self._copy_host_cert(docker, docker_host_cert, docker_host_cert)
            else:
                self.warn(f'Could not update certificates for {app}, app is not running')
        super().update_certificates(app)
