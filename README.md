# Automated Backport Validation and Committing

## Problem

As a maintainer of Dash Core, a large open source codebase fork of Bitcoin Core, there is a lot of information to keep track of!
Every change that Bitcoin Core merges into the codebase needs to be evaluated, and then backported (aka calling 
`git cherry-pick`), with any differences being resolved manually. While this is a LOT of work, it results in a lot of
very valuable contributions done to Bitcoin Core also being in the Dash Core codebase. Some of these changes are
actually critical fixes to CVEs which have not been made public yet. As decentralized systems can upgrade slowly, it's
important to get these fixes out before the issue is made publicly available.

Additionally, as we have a number of people who do these backports, it's important to keep everyone coordinated. As
such, we had created a [google spreadsheet](https://docs.google.com/spreadsheets/d/1DnKxat0S0H62CJOzXpKGPXTa8hgoVOjGYZzoClmGSB8/edit?usp=sharing)
in order to ensure everyone is coordinated.

However, this introduced a problem of consistency. Sometimes a developer would get a PR with some 20 backports merged
in, and then subsequently forget to update the spreadsheet. This results in duplicated effort.

Additionally, sometimes these backports have no conflicts which need to be manually resolved. As such, we can use this
script to also do these backports automatically to avoid wasting developer hours when a script can do the job.

## Libraries

- `gitpython` to clone and generally handle errors when it comes to git operations/
- `requests` to download the google spreadsheet
- `multiprocess` to in parallel handle the processing of the google spreadsheet

## Running
To run this script and see it in action, setup is simply, simply install requirements via:
```sh
pip install -r requirements.txt && python3 main.py
```

Follow the prompts: it will clone dashpay/dash and clone bitcoin. Be aware that cloning and fetching will take a while. 

If you don't have git setup on your system, it may not really work, if you're not able to commit because a name or
email isn't set, it won't work properly.


## P.S.

Apologies for not having submitted the proposal! I was very busy that week, and forgot about the deadline, and the
syllabus very clearly stated absolutely no late work would be graded, so I figured you did not want it yet.


## Merged-status updates (no backporting)

`python3 main.py --update-sheet-only` is what the hourly job and GitHub Actions run.
It reads `upstream/develop` (dashpay/dash) without touching the local checkout,
marks each row whose backport is merged as **Done (Merged to dashpay)**, clears its
Staged marker and staged date, keeps Notes and everything else, and exits before
any cherry-picking or PR creation. Rows are written in one batch per tab. Writes to
protected Status cells fail for that tab only; the service account needs edit access
to column A of every tracked tab.

`--check-only` reports mismatches and never writes; it wins if both flags are given.

To add a version, add its tab name and gid to `FILES` in `main.py`.

### Auditing a tab's rows against upstream

`sync_version_tabs.py` compares the tabs in `VERSION_RANGES` with the upstream PR
merges in each release range (`v32.0..master` until `v33.0` is tagged). It is
audit-only unless `--apply` is given, which appends missing rows with blank status
and never edits or deletes existing ones. Point it at a separate, current Bitcoin
Core clone:

```sh
python3 sync_version_tabs.py --bitcoin-repo /path/to/bitcoin [--apply]
```

### Tests

```sh
python3 -m unittest discover -s tests -v
```
