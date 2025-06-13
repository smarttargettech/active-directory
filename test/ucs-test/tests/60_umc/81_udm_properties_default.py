#!/usr/share/ucs-test/runner python3
## desc: Test the default values of properties
## bugs: [43395]
## roles:
##  - domaincontroller_master
## packages: [python3-univention-directory-manager]
## exposure: safe

import unittest
from argparse import Namespace as N

from univention.admin import property  # noqa: A004


class FakeObject(dict):
    set_defaults = True
    has_property = dict.__contains__


class TestProperty(unittest.TestCase):

    def test_default_sv(self):
        p = property()
        o = N(set_defaults=False)
        assert p.default(o) == ''

    def test_default_mv(self):
        p = property(multivalue=True)
        o = N(set_defaults=False)
        assert p.default(o) == []

    def test_base_default_sv(self):
        p = property()
        o = FakeObject()
        assert p.default(o) is None

    def test_base_default_mv(self):
        p = property(multivalue=True)
        o = FakeObject()
        assert p.default(o) == []

    def test_str_default_sv(self):
        p = property(default='x')
        o = FakeObject()
        assert p.default(o) == 'x'

    def test_str_default_mv(self):
        p = property(multivalue=True, default=('x', 'y'))
        o = N(set_defaults=True)
        assert p.default(o) == ['x', 'y']

    def test_complex_syntax(self):
        s = N(subsyntaxes=())
        p = property(multivalue=False, default=(('x', 'y'),), syntax=s)
        o = FakeObject()
        assert p.default(o) == ('x', 'y')

    def test_template_sv_empty(self):
        p = property(multivalue=False, default=('templ', ['prop']))
        o = FakeObject(prop='')
        assert p.default(o) is None

    def test_template_sv_set(self):
        p = property(multivalue=False, default=('<prop>', ['prop']))
        o = FakeObject(prop='value')
        assert p.default(o) == 'value'

    def test_template_mv_set(self):
        p = property(multivalue=True, default=('<prop1>', '<prop2>'))
        o = FakeObject(prop1='value1', prop2='value2')
        assert p.default(o) == ['value1', 'value2']

    def test_template_mv_incomplete(self):
        p = property(multivalue=True, default=('<prop>', None))
        o = FakeObject()
        assert p.default(o) == ['<prop>']

    def test_template_mv_empty(self):
        p = property(multivalue=True, default=('', None))
        o = FakeObject()
        assert p.default(o) == []

    def test_callable_set(self):
        x = object()
        o = FakeObject(prop='value1')
        f = lambda obj, extra: 'value2' if extra is x and obj is o else 'error'  # noqa: E731
        p = property(multivalue=False, default=(f, ['prop'], x))
        assert p.default(o) == 'value2'

    def test_callable_empty_sv(self):
        x = object()
        o = FakeObject(prop='')
        f = lambda obj, extra: 1 / 0  # noqa: E731
        p = property(multivalue=False, default=(f, ['prop'], x))
        assert p.default(o) is None

    def test_callable_empty_mv(self):
        x = object()
        o = FakeObject(prop='')
        f = lambda obj, extra: 1 / 0  # noqa: E731
        p = property(multivalue=True, default=(f, ['prop'], x))
        assert p.default(o) == []

    def test_fallback_sv(self):
        o = FakeObject()
        p = property(multivalue=False, default=(None,))
        assert p.default(o) is None

    def test_fallback_mv(self):
        o = FakeObject()
        p = property(multivalue=True, default=(None,))
        assert p.default(o) == []


if __name__ == '__main__':
    unittest.main()
