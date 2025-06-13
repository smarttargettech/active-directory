#!/usr/share/ucs-test/runner python3
## desc: "List all traceback in /var/log/univention/* logfile without failing"
## exposure: safe
## tags: [apptest]

import glob

import grep_traceback


grep_traceback.main(glob.glob('/var/log/univention/*.log*'))
