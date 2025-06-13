#!/usr/share/ucs-test/runner python3
## desc: check samba-tool drs showrepl
## exposure: safe
## tags:
##  - apptest
## packages:
## - univention-samba4

from subprocess import PIPE, Popen

from univention.testing import utils


proc = Popen(['samba-tool', 'drs', 'showrepl'], stdout=PIPE, stderr=PIPE)

stdout, stderr = proc.communicate()
stdout, stderr = stdout.decode("UTF-8"), stderr.decode("UTF-8")

print('** STDERR')
print(stderr.strip())
print('** STDOUT')
print(stdout.strip())
print('**')

if stderr.strip():
    errors = []
    for line in stderr.splitlines():
        if not line.endswith('WARNING: The "blocking locks" option is deprecated'):
            errors.append(line)
    if errors:
        utils.fail('samba-tool drsi showrepl returned on stderr: %s' % '\n'.join(errors))

if 'ERR_' in stdout:
    utils.fail('samba-tool drsi showrepl returned a string with ERR_')
