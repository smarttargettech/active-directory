#!/usr/bin/env python3
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# SPDX-FileCopyrightText: 2024-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import sys

from ucsschool.lib.models.user import Student
from univention.admin.uldap import getAdminConnection


lo, po = getAdminConnection()

student = Student(name='Teststudent', firstname='Test', lastname='Student', school='School1')
student.create(lo)

student2 = Student(name='Teststudent2', firstname='Test2', lastname='Student2', school='School2')
student2.create(lo)

student3 = Student(name='Teststudent3', firstname='Test3', lastname='Student3', school='School1', schools=['School1', 'School2'])
student3.create(lo)

s = lo.get(student.dn)
if [b'School1'] != s['ucsschoolSchool']:
    print('Error: Student should only be in School1')
    sys.exit(1)

s2 = lo.get(student2.dn)
if [b'School2'] != s2['ucsschoolSchool']:
    print('Error: Student should only be in School2')
    sys.exit(1)

s3 = lo.get(student3.dn)
if {b'School1', b'School2'} != set(s3['ucsschoolSchool']):
    print('Error: Student should be in School1 and School2')
    sys.exit(1)

sys.exit(0)
