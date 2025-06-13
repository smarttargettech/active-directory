#!/usr/share/ucs-test/runner python3
## desc: Check if perfect forward secrecy (PFS) is enabled.
## tags: [apptest]
## exposure: safe
## packages: [openssl, univention-mail-server, univention-mail-postfix]
## bugs: [35924]


from subprocess import PIPE, Popen

from univention.testing import utils


# Possible Ciphers for UCS 4.0:
# (info on PFS http://www.postfix.org/FORWARD_SECRECY_README.html)
PFS_CIPHERS = (
    'AECDH-AES256-SHA',
    'ECDHE-RSA-AES256-GCM-SHA384',
    'ECDHE-ECDSA-AES256-GCM-SHA384',
    'ECDHE-RSA-AES256-SHA384',
    'ECDHE-ECDSA-AES256-SHA384',
    'ECDHE-RSA-AES256-SHA',
    'ECDHE-ECDSA-AES256-SHA',
    'AECDH-DES-CBC3-SHA',
    'ECDHE-RSA-DES-CBC3-SHA',
    'ECDHE-ECDSA-DES-CBC3-SHA',
    'AECDH-AES128-SHA',
    'ECDHE-RSA-AES128-GCM-SHA256',
    'ECDHE-ECDSA-AES128-GCM-SHA256',
    'ECDHE-RSA-AES128-SHA256',
    'ECDHE-ECDSA-AES128-SHA256',
    'ECDHE-RSA-AES128-SHA',
    'ECDHE-ECDSA-AES128-SHA',
    'AECDH-RC4-SHA',
    'ECDHE-RSA-RC4-SHA',
    'ECDHE-ECDSA-RC4-SHA',
    'TLSv1.3, Cipher is',   # TLSv1.3 always uses forward-secrecy!
)


def check_pfs_cipher():
    """Makes a localhost connection with openssl client and looks for cipher used."""
    print("\nExpecting one of the following ciphers to be used:", PFS_CIPHERS)
    openssl_out = run_openssl().decode('UTF-8')
    print('-----------CUTCUTCUT----------------')
    print(openssl_out)
    print('-----------CUTCUTCUT----------------')
    for possible_cipher in PFS_CIPHERS:
        if possible_cipher in openssl_out:
            print("\nCipher '%s' was found.\n" % possible_cipher)
            return

    utils.fail("None of the possible ciphers were found in the output from TLS client. Probably TLS/PFS does not work.")


def run_openssl():
    """Runs the openssl s_client (TLS) and returns the output grep'ed for cipher."""
    # reconnect used to avoid waiting for a timeout:
    cmd = ('openssl', 's_client', '-starttls', 'smtp', '-crlf', '-connect', '127.0.0.1:25', '-reconnect')

    # run the openssl client:
    proc = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)
    stdout, stderr = proc.communicate()

    if stderr:
        print("The following message(s) appeared in STDERR:\n", stderr.decode('UTF-8', 'replace'))
    if not stdout:
        utils.fail("The 'openssl' client did not produce any output to STDOUT")

    print("Openssl client STDOUT:\n", stdout)
    # grep for cipher:
    cmd = ('grep', '--ignore-case', 'cipher')
    proc = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)
    grep_stdout, stderr = proc.communicate(stdout)

    if stderr:
        print(("The following message(s) appeared in STDERR while grep'ing for 'cipher':\n", stderr.decode('UTF-8', 'replace')))
    if not grep_stdout:
        utils.fail("No 'cipher' string was found in the output from openssl client. Probably TLS/PFS does not work.")

    return grep_stdout


if __name__ == '__main__':
    check_pfs_cipher()
