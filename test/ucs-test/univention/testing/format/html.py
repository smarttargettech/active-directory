# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# SPDX-FileCopyrightText: 2024-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""Format UCS Test results as HTML."""


import sys
from typing import IO
from xml.sax.saxutils import escape as escape_xml

from univention.testing.data import TestEnvironment, TestFormatInterface, TestResult


__all__ = ['HTML']

URI_BUG = 'https://forge.univention.org/bugzilla/show_bug.cgi?id=%s'
URI_OTRS = 'https://gorm.knut.univention.de/otrs/index.pl?Action=AgentTicketSearch&Subaction=Search&TicketNumber=%s'


class HTML(TestFormatInterface):
    """Create simple HTML report."""

    def __init__(self, stream: IO[str] = sys.stdout) -> None:
        super().__init__(stream)

    def begin_run(self, environment: TestEnvironment, count: int = 1) -> None:
        """Called before first test."""
        super().begin_run(environment, count)
        print('<html>', file=self.stream)
        print('<head>', file=self.stream)
        print('<title>ucs-test</title>', file=self.stream)
        print('</head>', file=self.stream)
        print('<body>', file=self.stream)

    def begin_section(self, section: str) -> None:
        """Called before each section."""
        super().begin_section(section)
        print(f'<h2>Section {escape_xml(section)}</h2>', file=self.stream)
        print('<table>', file=self.stream)

    def end_test(self, result: TestResult) -> None:
        """Called after each test."""
        title = escape_xml(result.case.uid)
        if result.case.description:
            title = '<span title="%s">%s</span>' % \
                    (title, escape_xml(result.case.description))
        if result.case.bugs or result.case.otrs:
            links = []
            links += [
                '<a href="%s">Bug #%s</a>' %
                (escape_xml(URI_BUG % bug), bug)
                for bug in result.case.bugs]
            links += [
                '<a href="%s">OTRS #%s</a>' %
                (escape_xml(URI_OTRS % tick), tick)
                for tick in result.case.otrs]
            title = '%s (%s)' % (title, ', '.join(links))
        msg = '<span style="color:%s;">%s</span>' % \
            (result.reason.color.lower(), escape_xml(str(result.reason)))
        print(f'<tr><td>{title}</td><td>{msg}</td></tr>', file=self.stream)
        super().end_test(result)

    def end_section(self) -> None:
        """Called after each section."""
        print('</table>', file=self.stream)
        super().end_section()

    def end_run(self) -> None:
        """Called after all test."""
        print('</body>', file=self.stream)
        print('</html>', file=self.stream)
        super().end_run()

    def format(self, result: TestResult) -> None:
        """
        Format single test.

        >>> from univention.testing.data import TestCase
        >>> te = TestEnvironment()
        >>> tc = TestCase('python/data.py')
        >>> tr = TestResult(tc, te)
        >>> tr.success()
        >>> HTML().format(tr)
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
