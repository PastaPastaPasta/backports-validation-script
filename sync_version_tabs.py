#!/usr/bin/env python3
"""Audit requested tabs against upstream PR merges; append missing rows on request."""

import argparse
import re
import subprocess

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from main import DOCUMENT_ID

# Names are the existing worksheet titles, not inferred from Bitcoin tag names.
VERSION_RANGES = {
    '0.29': ('v28.0', 'v29.0'),
    '0.30': ('v29.0', 'v30.0'),
    'v31': ('v30.0', 'v31.0'),
    'v32': ('v31.0', 'v32.0'),
    'v33': ('v32.0', 'v33.0'),
}
PR_MERGE = re.compile(r'^Merge (?:bitcoin/bitcoin|bitcoin-core/gui)?#\d+:')


def git_output(repo, *args):
    return subprocess.check_output(['git', '-C', repo, *args], text=True).strip()


def upstream_merges(repo, start, end):
    """Pin endpoints once, including master when v33 has not been released."""
    if end == 'v33.0':
        exists = subprocess.run(
            ['git', '-C', repo, 'show-ref', '--verify', '--quiet', 'refs/tags/v33.0'],
            check=False,
        ).returncode
        if exists not in (0, 1):
            raise ValueError('Cannot check for v33.0 in the upstream repository')
        if exists == 1:
            end = 'master'
    start_sha = git_output(repo, 'rev-parse', '--verify', f'{start}^{{commit}}')
    end_sha = git_output(repo, 'rev-parse', '--verify', f'{end}^{{commit}}')
    output = git_output(repo, 'log', '--reverse', '--merges', '--format=%H%x09%s',
                        f'{start_sha}..{end_sha}')
    commits = [line.split('\t', 1) for line in output.splitlines() if line]
    commits = [(sha, message) for sha, message in commits if PR_MERGE.match(message)]
    return start_sha, end_sha, end, commits


def missing_rows(rows, commits):
    """Reject inconsistent data rather than editing or deleting annotated rows."""
    if not rows or rows[0][:4] != ['Status', 'Staged', 'Commit Hash', 'Message']:
        raise ValueError('Unexpected worksheet headers')
    seen = set()
    for row in rows[1:]:
        if len(row) < 3 or not row[2]:
            continue
        short_sha = row[2]
        matches = [sha for sha, _ in commits if sha.startswith(short_sha)]
        if len(short_sha) < 10 or len(matches) != 1:
            raise ValueError(f'Commit outside expected range or ambiguous: {short_sha}')
        sha = matches[0]
        if sha in seen:
            raise ValueError(f'Duplicate commit in worksheet: {short_sha}')
        seen.add(sha)
    # Do not infer merged/DNM status or copy annotations from another version.
    return [['', '', sha[:10], message, '', '', '', '', '', '']
            for sha, message in commits if sha not in seen]


def sync_tabs(spreadsheet, repo, apply=False):
    plans = []
    for title, (start, end) in VERSION_RANGES.items():
        start_sha, end_sha, resolved_end, commits = upstream_merges(repo, start, end)
        worksheet = spreadsheet.worksheet(title)
        rows = worksheet.get_all_values()
        additions = missing_rows(rows, commits)
        provisional = ' (provisional)' if resolved_end == 'master' else ''
        print(f'{title}: {start}..{resolved_end}{provisional}; '
              f'{start_sha}..{end_sha}; {len(commits)} PR merges; '
              f'{len(additions)} missing')
        plans.append((worksheet, rows, additions))
    # Audit every tab before making any writes. Never clear/rebuild a worksheet.
    for worksheet, rows, additions in plans:
        if apply and additions:
            if worksheet.get_all_values() != rows:
                raise ValueError(f'{worksheet.title} changed during audit; retry')
            worksheet.append_rows(additions, value_input_option='RAW',
                                  insert_data_option='INSERT_ROWS', table_range='A1:J')
    return sum(len(additions) for _, _, additions in plans)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bitcoin-repo', required=True,
                        help='Local Bitcoin repository with current release tags and master')
    parser.add_argument('--credentials', default='.secrets/service_account.json',
                        help='Existing service-account key path (never printed)')
    parser.add_argument('--apply', action='store_true', help='Append missing rows; default is audit only')
    args = parser.parse_args()
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(args.credentials, scope)
    spreadsheet = gspread.authorize(creds).open_by_key(DOCUMENT_ID)
    sync_tabs(spreadsheet, args.bitcoin_repo, apply=args.apply)


if __name__ == '__main__':
    main()
