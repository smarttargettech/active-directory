# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# SPDX-FileCopyrightText: 2024-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""Format UCS Test results as JUnit report."""


import errno
import os
import shutil
import sys
from datetime import datetime
from typing import IO, Any
from xml.sax.saxutils import XMLGenerator
from xml.sax.xmlreader import AttributesImpl

from univention.testing.data import TestCase, TestFormatInterface, TestResult
from univention.testing.format.text import Raw


__all__ = ['Junit']


class Junit(TestFormatInterface):
    """
    Create Junit report.
    <http://windyroad.org/dl/Open%20Source/JUnit.xsd>
    """

    def __init__(self, stream: IO[str] = sys.stdout) -> None:
        super().__init__(stream)
        self.outdir = "test-reports"
        self.now = datetime.today()
        self.raw = Raw(stream)

    def begin_test(self, case: TestCase, prefix: str = '') -> None:
        """Called before each test."""
        super().begin_test(case, prefix)
        self.now = datetime.today().replace(microsecond=0)
        print('\r', end='', file=self.stream)
        self.raw.begin_test(case, prefix)
        self.stream.flush()

    def end_run(self):
        print('')  # clear \r
        self.stream.flush()

    def end_test(self, result: TestResult) -> None:
        """Called after each test."""
        self.raw.end_test(result, end='')
        failures = errors = skipped = disabled = 0
        if result.reason.eofs == 'O':
            pass
        elif result.reason.eofs == 'S':
            skipped = 1
        elif result.reason.eofs == 'F':
            failures = 1
        elif result.reason.eofs == 'E':
            errors = 1
        else:
            errors = 1
        classname = result.case.uid.replace("/", ".")
        classname = classname.removesuffix('.py')

        filename = os.path.join(self.outdir, f'{result.case.uid}.xml')
        if result.case.is_pytest and os.path.exists(filename):
            return  # pytest itself already writes the junit file! create one if pytest did not

        dirname = os.path.dirname(filename)
        try:
            os.makedirs(dirname)
        except OSError as ex:
            if ex.errno != errno.EEXIST:
                raise

        if result.case.external_junit and os.path.exists(result.case.external_junit):
            shutil.copyfile(result.case.external_junit, filename)
            return

        with open(filename, 'w') as f_report:
            xml = XMLGenerator(f_report, encoding='utf-8')
            xml.startDocument()
            xml.startElement('testsuite', AttributesImpl({
                'name': classname,
                'tests': '%d' % (1,),
                'failures': '%d' % (failures,),
                'errors': '%d' % (errors,),
                'time': f'{result.duration / 1000.0:0.3f}',
                'disabled': '%d' % (disabled,),
                'skipped': '%d' % (skipped,),
                'timestamp': self.now.isoformat(),
                'hostname': os.uname()[1],
            }))

            xml.startElement('properties', AttributesImpl({}))
            xml.startElement('property', AttributesImpl({
                'name': 'hostname',
                'value': result.environment.hostname,
            }))
            xml.endElement('property')
            xml.startElement('property', AttributesImpl({
                'name': 'architecture',
                'value': result.environment.architecture,
            }))
            xml.endElement('property')
            xml.startElement('property', AttributesImpl({
                'name': 'role',
                'value': result.environment.role,
            }))
            xml.endElement('property')
            xml.startElement('property', AttributesImpl({
                'name': 'version',
                'value': f'{result.environment.ucs_version}',
            }))
            xml.endElement('property')
            if result.case.description:
                xml.startElement('property', AttributesImpl({
                    'name': 'description',
                    'value': result.case.description or result.case.uid,
                }))
                xml.endElement('property')
            xml.endElement('properties')

            xml.startElement('testcase', AttributesImpl({
                'name': result.environment.hostname,
                # 'assertions': '%d' % (0,),
                'time': f'{result.duration / 1000.0:0.3f}',
                'classname': classname,
                # 'status': '???',
            }))

            if skipped:
                try:
                    _mime, content = result.artifacts['check']
                except KeyError:
                    msg = ''
                else:
                    msg = '\n'.join([f'{c}' for c in content])
                xml.startElement('skipped', AttributesImpl({
                    'message': msg,
                }))
                xml.endElement('skipped')
            elif errors:
                xml.startElement('error', AttributesImpl({
                    'type': 'TestError',
                    'message': f'{result.result}',
                }))
                xml.endElement('error')
            elif failures:
                xml.startElement('failure', AttributesImpl({
                    'type': 'TestFailure',
                    'message': f'{result.reason!s} ({result.case.description or result.case.uid})',
                }))
                xml.endElement('failure')

            try:
                _mime, content = result.artifacts['stdout']
            except KeyError:
                pass
            else:
                xml.startElement('system-out', AttributesImpl({}))
                xml.characters(self.utf8(content))
                xml.endElement('system-out')

            try:
                _mime, content = result.artifacts['stderr']
            except KeyError:
                pass
            else:
                xml.startElement('system-err', AttributesImpl({}))
                xml.characters(self.utf8(content))
                xml.endElement('system-err')

            xml.endElement('testcase')
            xml.endElement('testsuite')
            xml.endDocument()
        super().end_test(result)

    def utf8(self, data: Any) -> str:
        if isinstance(data, str):
            data = data.encode('utf-8', 'replace').decode('utf-8')
        elif isinstance(data, bytes):
            data = data.decode('utf-8', 'replace').encode('utf-8')
        return data

    def format(self, result: TestResult) -> None:
        """
        >>> from univention.testing.data import TestEnvironment
        >>> te = TestEnvironment()
        >>> tc = TestCase('python/data.py')
        >>> tr = TestResult(tc, te)
        >>> tr.success()
        >>> Junit().format(tr)

        """
        self.begin_run(result.environment)
        self.begin_section('')
        self.begin_test(result.case)
        self.end_test(result)
        self.end_section()
        self.end_run()


if __name__ == '__main__':
    import doctest
    doctest.testmod()
