#!/usr/share/ucs-test/runner pytest-3 -s -l -vvv
## desc: Download metadata
## tags: [saml]
## exposure: safe

from urllib.request import urlopen

from univention.testing.utils import fail


def test_download_metadata(ucr):
    metadata_url = ucr['umc/saml/idp-server']
    if metadata_url is None:
        fail('The ucr key umc/saml/idp-server is not set')

    res = []

    # read at least five times because ucs-sso is an alias for different IPs
    for i in range(5):
        print('%d: Query metadata for %r' % (i, metadata_url))
        response = urlopen(metadata_url)  # noqa: S310
        metadata = response.read()
        if not metadata:
            fail('Empty response')
        print(metadata.decode('UTF-8', 'replace'))
        res.append(metadata)

    for i in range(4):
        if res[i] != res[i + 1]:
            fail('Metadata is different: %d and %d' % (i, i + 1))
