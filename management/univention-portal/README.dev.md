# Component moved

The component `univention-portal` is now maintained in a separate dedicated repository,
See `univention/components/univention-portal#737` for the status of the migration.

## Building & CI/CD

Import into repo-ng bildsystem via:

```
repo_admin.py \
    -G git@git.knut.univention.de:univention/components/univention-portal.git \
    -b develop \
    -p univention-portal \
    -P . \
    -r 5.2-0 -s errata5.2-0-or-similar
```
