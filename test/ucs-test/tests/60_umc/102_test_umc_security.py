#!/usr/share/ucs-test/runner pytest-3 -s -l -vvv --tb=native
## desc: Test security related HTTP headers are set
## exposure: dangerous
## packages: [univention-management-console-server]

import copy
from collections import defaultdict
from http.client import HTTPConnection

import pytest

from univention.lib.umc import Unauthorized
from univention.testing import network, utils


class TestSecurityHeaders:

    @pytest.mark.parametrize('path', [
        'login/',
        'login/index.html',
        'login/blank.html',
        'login/login.html',
    ])
    def test_login_site(self, path, Client, ucr):
        client = Client()
        response = client.request('GET', path)
        assert response.get_header("X-Frame-Options") is None  # changed from: == "SAMEORIGIN"
        sso = '%(ucs/server/sso/uri)s/' % defaultdict(lambda: '', ucr)
        assert response.get_header("Content-Security-Policy") == "default-src 'self' 'unsafe-inline' 'unsafe-eval' %s  https://www.piwik.univention.de/ ; frame-ancestors 'self';" % sso

        assert response.get_header("X-Permitted-Cross-Domain-Policies") == "master-only"
        assert response.get_header("X-XSS-Protection") == "1; mode=block"
        assert response.get_header("X-Content-Type-Options") == "nosniff"

    @pytest.mark.parametrize('path', [
        '/languages.json',
        '/portal/',
        '/management/',
    ])
    def test_univention(self, path, ucr, Client):
        client = Client()
        response = client.request('GET', path)
        assert response.get_header("X-Permitted-Cross-Domain-Policies") == "master-only"
        assert response.get_header("X-XSS-Protection") == "1; mode=block"
        assert response.get_header("X-Content-Type-Options") == "nosniff"
        assert response.get_header("X-Frame-Options") is None  # changed from: == "DENY"
        if path == '/languages.json':
            assert response.get_header("Content-Security-Policy") == "frame-ancestors 'none';"
        else:
            sso = '%(ucs/server/sso/uri)s/' % defaultdict(lambda: '', ucr)
            if 'portal' in path:
                sso = '%(ucs/server/sso/uri)s/' % defaultdict(lambda: '', ucr)
            sso = sso.replace('http:///', '').replace('https:///', '').strip()
            expected = "frame-ancestors 'self' %s;" % sso
            assert expected in response.get_header("Content-Security-Policy")

    @pytest.mark.xfail(reason='Bug #52940')
    def test_ip_bound_to_session(self, Client, ucr, restart_umc_server):
        client = Client('%(hostname)s.%(domainname)s' % ucr)
        client.ConnectionType = HTTPConnection  # workaround TLS hostname mismatch

        account = utils.UCSTestDomainAdminCredentials()
        client.authenticate(account.username, account.bindpw)
        # make sure any UMC module is present (the session is not dropped to anonymous)
        assert any(x['id'] == 'top' for x in client.umc_get('modules').data['modules'])

        # change the external IP address
        with network.NetworkRedirector() as nethelper:
            nethelper.add_loop('1.2.3.4', '4.3.2.1')
            c = Client('1.2.3.4')
            c.ConnectionType = HTTPConnection  # workaround TLS hostname mismatch
            c.cookies = copy.deepcopy(client.cookies)
            with pytest.raises(Unauthorized) as exc:
                c.umc_get('modules')
            assert 'The current session is not valid with your IP address for security reasons.' in str(exc.value)

            # check if the session is still bound after the internal connection to the UMC-Server was lost
            restart_umc_server()
            c.cookies = copy.deepcopy(client.cookies)
            with pytest.raises(Unauthorized) as exc:
                c.umc_get('modules')
            assert 'The current session is not valid with your IP address for security reasons.' in str(exc.value)

        # make sure any UMC module is present (the session is not dropped to anonymous)
        assert any(x['id'] == 'top' for x in client.umc_get('modules').data['modules'])

        # make sure the same rules apply for localhost
        c2 = Client('localhost')
        c2.ConnectionType = HTTPConnection  # workaround TLS hostname mismatch
        c2.cookies = copy.deepcopy(client.cookies)
        assert any(x['id'] == 'top' for x in c2.umc_get('modules').data['modules'])

        # check if the session is still bound after the internal connection to the UMC-Server was lost
        restart_umc_server()
        c2.cookies = copy.deepcopy(client.cookies)
        assert any(x['id'] == 'top' for x in c2.umc_get('modules').data['modules'])

        # make sure any UMC module is present (the session is not dropped to anonymous)
        assert any(x['id'] == 'top' for x in client.umc_get('modules').data['modules'])
