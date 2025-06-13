#!/usr/share/ucs-test/runner python3
## desc: Check if main.cf.local is included
## exposure: unsafe
## packages: [univention-mail-postfix]

import os
import subprocess
import tempfile

from univention.testing import utils


def check_file(basename: str, snippet: str) -> None:
    fn_base = basename
    fn_base_local = f'{basename}.local'
    fn_moved_local = None
    content = open(fn_base).read()
    if snippet in content:
        utils.fail(f'{fn_base!r} already contains the test snippet before starting the test')

    try:
        # rescue existing main.cf.local
        if os.path.exists(fn_base_local):
            fn_moved_local = tempfile.mkstemp(
                prefix=os.path.basename(fn_base_local),
                dir=os.path.dirname(fn_base_local))[1]
            os.rename(fn_base_local, fn_moved_local)

        # write snippet to main.cf.local
        with open(fn_base_local, 'w') as fd:
            fd.write(snippet)

        # commit changes to main.cf.local
        subprocess.call(['ucr', 'commit', fn_base])

        content = open(fn_base).read()
        if snippet not in content:
            utils.fail(f'{fn_base!r} does not contain snippet!')

    finally:
        os.remove(fn_base_local)
        if fn_moved_local:
            os.rename(fn_moved_local, fn_base_local)
        # commit changes to main.cf.local
        subprocess.call(['ucr', 'commit', fn_base])


def main() -> None:
    snippet = '''smtp_tls_loglevel = 0
# MY FUNNY TEST COMMENT
smtpd_tls_loglevel = 0
'''
    check_file('/etc/postfix/main.cf', snippet)

    snippet = '''#25252525      inet  n       -       n       -       -       smtpd --some-obscure-option --definitely-unknown-to-postfix
'''
    check_file('/etc/postfix/master.cf', snippet)


if __name__ == '__main__':
    main()
