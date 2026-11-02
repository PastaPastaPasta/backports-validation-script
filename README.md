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

Use `python3 main.py --update-sheet-only` for the hourly updater. This mode reads
`upstream/develop`, updates only the **Status** cell of confirmed merged backports,
and returns before any cherry-picking or GitHub PR creation. It does not clear
Staged, Notes, or other manual annotations. `--check-only` makes no sheet changes,
even when mismatches are found; it takes precedence if both flags are supplied.
The GitHub Actions invocation also uses `--update-sheet-only`.

### Versions 29–33

The actual worksheet names and upstream PR-merge ranges are:

| Tab | gid | Upstream range | PR merges audited 2026-11-02 |
| --- | --- | --- | ---: |
| `0.29` | `896801947` | `v28.0..v29.0` | 596 |
| `0.30` | `1032898469` | `v29.0..v30.0` | 577 |
| `v31` | `82764727` | `v30.0..v31.0` | 620 |
| `v32` | `1425249267` | `v31.0..v32.0` | 722 |
| `v33` | `260703346` | `v32.0..master` (provisional) | 216 |

The first four tabs are complete. There is no upstream `v33.0` tag at the audit
snapshot. The provisional v33 endpoint is
`e310efb202bd1283bcdd25d5748078df1219c8ac`, not an invented release tag.
The existing v33 tab contains 214 PR merges, through `cd74d9650e`; two are missing:

- `d54844eaeb`: Merge bitcoin/bitcoin#36091: test: Add debug output to common tested types
- `e310efb202`: Merge bitcoin/bitcoin#36618: test: Wait for index sync in all tests

An append attempt was rejected by Google Sheets protection (HTTP 400), so these
rows are **not live**. A sheet owner must allow the service account to append or
apply the missing rows themselves. No protections were removed and no existing
data was rewritten. The audit follows the existing convention of PR merge
commits, including GUI merges; subtree-only merges are not separate tracker rows.

To audit or append using the existing credential flow, first fetch current tags
and `master` into a **separate Bitcoin repository** (do not reset the live Dash
checkout), then run:

```sh
python3 sync_version_tabs.py --bitcoin-repo /path/to/bitcoin
# Only when the audit is correct and sheet write permission is available:
python3 sync_version_tabs.py --bitcoin-repo /path/to/bitcoin --apply
```

Both scripts default to `.secrets/service_account.json`; the audit tool accepts
`--credentials /path/to/existing/key` when run from an isolated checkout. Do not
commit credentials. The tool does not fetch Git refs itself, so its input repo
must be current. It pins both endpoints for each audit and uses `v33.0` once that
tag exists; until then, v33 is explicitly provisional and requires re-auditing as
master advances. It checks all five existing tabs before writing, rejects duplicate
or out-of-range commit hashes, and only appends missing rows with blank status and
annotations. It never clears, renames, or recreates tabs. Its default is audit-only;
it is independent of the hourly merged-status updater.

### Deployment status

The live local checkout and its untracked `run-validation.sh` are not changed by
this PR. That checkout still tracks only versions through `0.28`. After review,
an owner must approve rollout and carefully integrate the tracked changes with
the live checkout's pre-existing modifications, retaining the wrapper's
`--update-sheet-only` invocation. Merging this PR does not by itself deploy that
local hourly job. Do not replace or reset its files.

### Tests

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile main.py sync_version_tabs.py tests/test_tracker.py
```
