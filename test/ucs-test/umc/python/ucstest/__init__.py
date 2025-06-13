#!/usr/bin/python3
#
# Univention Management Console
#  module: ucs-test
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

import subprocess
import sys
import time

from univention.config_registry import ucr
from univention.management.console.error import UMC_Error
from univention.management.console.modules import Base
from univention.management.console.modules.decorators import simple_response


class NonThreadedError(Exception):
    pass


class ThreadedError(Exception):
    pass


class FakeThread:
    def __init__(self):
        self.exc_info = None
        self.name = "Fake Thread"
        self.trace = None


def joinscript():
    process = subprocess.Popen(['/bin/sh'], stdin=subprocess.PIPE)
    process.communicate(b'''
    . /usr/share/univention-lib/umc.sh

    umc_init
    umc_operation_create "ucstest-all" "UCS Test" "" "ucstest/*"
    umc_policy_append "default-umc-all" "ucstest-all"
    exit 0
    ''')


def unjoinscript():
    pass


if ucr.get_int('ucstest/sleep-during-import', 0) > 0:
    time.sleep(ucr.get_int('ucstest/sleep-during-import'))


class Instance(Base):

    def init(self):
        if ucr.get_int('ucstest/sleep-during-init', 0) > 0:
            time.sleep(ucr.get_int('ucstest/sleep-during-init'))

    @simple_response
    def respond(self):
        return True

    def norespond(self, request):
        pass

    @simple_response
    def non_threaded_traceback(self):
        raise NonThreadedError()

    @simple_response
    def threaded_traceback(self):
        def _throw_exception(_1, _2):
            raise ThreadedError()
        return _throw_exception

    @simple_response
    def umc_error_traceback(self):
        raise UMC_Error("This is an UMC Error")

    @simple_response
    def sleep(self, seconds=1):
        time.sleep(seconds)
        return True

    def traceback_as_thread_result(self, request):
        # UVMM uses this to pass-through traceback from internal umc calls to the frontend
        result = None
        try:
            raise ThreadedError()
        except ThreadedError:
            etype, result, _ = sys.exc_info()
            thread = FakeThread()
            thread.exc_info = (etype, result, None)
        self.thread_finished_callback(thread, result, request)

    def umc_error_as_thread_result(self, request):
        # UVMM uses this to pass-through traceback from internal umc calls to the frontend
        result = None
        try:
            raise UMC_Error("This is an UMC Error")
        except UMC_Error:
            etype, result, _ = sys.exc_info()
            thread = FakeThread()
            thread.exc_info = (etype, result, None)
        self.thread_finished_callback(thread, result, request)
