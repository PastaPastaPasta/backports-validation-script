import csv
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import main
import sync_version_tabs as sync


HEADER = ['Status', 'Staged', 'Commit Hash', 'Message', 'Notes', 'Problem', 'empty']
MERGED_ROW_2 = [{'range': 'A2', 'values': [['Done (Merged to dashpay)']]},
                {'range': 'B2', 'values': [['']]},
                {'range': 'G2', 'values': [['']]}]
STAGED_ROW = ['', 'K_Staged', '1234567890', 'Merge bitcoin/bitcoin#123: example', 'keep me', 'FALSE', '10/24/2025']


def example(commit_hash='1234567890'):
    return main.backport_object(main.StatusDone.NONE, main.StatusStaged.NONE, commit_hash,
                                'Merge bitcoin/bitcoin#123: example', '', False, 'v33.csv', False)


def run_update(rows, objs, error=None):
    spreadsheet = MagicMock()
    worksheet = spreadsheet.worksheet.return_value
    worksheet.get_values.return_value = rows
    worksheet.batch_update.side_effect = error
    out = io.StringIO()
    with redirect_stdout(out):
        main.update_merged_rows(spreadsheet, 'v33', objs)
    return worksheet, out.getvalue()


class TrackerTests(unittest.TestCase):
    def run_mode(self, flags, merged=True, version='v33'):
        spreadsheet = MagicMock()
        repo = MagicMock()
        repo.git.log.return_value = 'abc Backport bitcoin#123: example' if merged else 'abc Other change'
        worksheet = spreadsheet.worksheet.return_value
        worksheet.get_values.return_value = [HEADER, STAGED_ROW]
        with tempfile.TemporaryDirectory() as directory:
            files = [(str(Path(directory) / (version + '.csv')), '260703346')]
            with open(files[0][0], 'w') as f:
                csv.writer(f).writerows([
                    ['Status', 'Staged', 'Commit Hash', 'Message', 'Notes'],
                    ['', 'Staged', '1234567890', 'Merge bitcoin/bitcoin#123: example', 'keep me'],
                ])
            with patch.object(main, 'FILES', files), \
                 patch.object(main, 'download_sheet_as_csv'), \
                 patch.object(main.ServiceAccountCredentials, 'from_json_keyfile_name'), \
                 patch.object(main.gspread, 'authorize') as authorize, \
                 patch.object(main.git, 'Repo', return_value=repo), \
                 patch.object(main.os.path, 'isdir', return_value=True), \
                 patch.object(main, 'Github') as github, \
                 patch.object(main, 'Pool') as pool, \
                 patch('sys.argv', ['main.py'] + flags), redirect_stdout(io.StringIO()):
                authorize.return_value.open_by_key.return_value = spreadsheet
                pool.return_value.__enter__.return_value.map.side_effect = lambda fn, xs: list(map(fn, xs))
                main.main()
                github.assert_not_called()
        repo.git.checkout.assert_not_called()
        repo.git.cherry_pick.assert_not_called()
        repo.git.reset.assert_not_called()
        repo.remotes.origin.pull.assert_not_called()
        repo.remotes.upstream.fetch.assert_called_once_with('+refs/heads/develop:refs/remotes/upstream/develop')
        repo.git.log.assert_called_once_with('upstream/develop', '--oneline')
        if merged and '--check-only' not in flags:
            spreadsheet.worksheet.assert_called_once_with(files[0][0].replace('.csv', ''))
        return worksheet

    def test_requested_tabs(self):
        self.assertEqual(dict(main.FILES), {
            **dict(main.FILES[:13]), '0.29.csv': '896801947', '0.30.csv': '1032898469',
            'v31.csv': '82764727', 'v32.csv': '1425249267', 'v33.csv': '260703346',
        })
        self.assertEqual(len(main.FILES), 18)

    def test_sheet_only_marks_merged_and_clears_staging(self):
        worksheet = self.run_mode(['--update-sheet-only'])
        worksheet.get_values.assert_called_once_with('A:G')
        self.assertEqual(worksheet.batch_update.call_args_list,
                         [call(MERGED_ROW_2[:2]), call(MERGED_ROW_2[2:])])

    def test_empty_staging_cells_are_not_written(self):
        # Some tabs protect B/G; untouched empty cells keep the batch writable.
        worksheet, _ = run_update([HEADER, ['', '', '1234567890', 'm']], [example()])
        worksheet.batch_update.assert_called_once_with(MERGED_ROW_2[:1])

    def test_protected_date_column_still_marks_status(self):
        def protected_g(data):
            if data[0]['range'].startswith('G'):
                raise main.APIError(MagicMock())
        worksheet, out = run_update([HEADER, STAGED_ROW], [example()], error=protected_g)
        worksheet.batch_update.assert_any_call(MERGED_ROW_2[:2])
        self.assertIn("Could not clear staged dates in 'v33'", out)
        self.assertNotIn('Failed to update sheet', out)

    def test_ambiguous_or_missing_hash_is_skipped(self):
        for rows in [[HEADER], [HEADER, STAGED_ROW, STAGED_ROW]]:
            with self.subTest(rows=rows):
                worksheet, _ = run_update(rows, [example()])
                worksheet.batch_update.assert_not_called()

    def test_blank_hash_or_unexpected_layout_writes_nothing(self):
        cases = [('', [HEADER, ['', '', ''], STAGED_ROW]),
                 ('1234567890', [['Status', 'Notes', 'Commit Hash'], STAGED_ROW]),
                 ('1234567890', [])]
        for commit_hash, rows in cases:
            with self.subTest(commit_hash=commit_hash, rows=rows):
                worksheet, _ = run_update(rows, [example(commit_hash)])
                worksheet.batch_update.assert_not_called()

    def test_protected_sheet_failure_is_contained(self):
        _, out = run_update([HEADER, STAGED_ROW], [example()], error=main.APIError(MagicMock()))
        self.assertIn("Failed to update sheet 'v33'", out)

    def test_all_requested_versions_participate_in_status_updates(self):
        for version in sync.VERSION_RANGES:
            with self.subTest(version=version):
                worksheet = self.run_mode(['--update-sheet-only'], version=version)
                worksheet.batch_update.assert_any_call(MERGED_ROW_2[:2])

    def test_check_only_does_not_write_even_on_mismatch(self):
        worksheet = self.run_mode(['--check-only'])
        worksheet.batch_update.assert_not_called()

    def test_check_only_takes_precedence(self):
        worksheet = self.run_mode(['--check-only', '--update-sheet-only'])
        worksheet.batch_update.assert_not_called()

    def test_sheet_only_no_mismatch(self):
        worksheet = self.run_mode(['--update-sheet-only'], merged=False)
        worksheet.batch_update.assert_not_called()


class PopulationTests(unittest.TestCase):
    header = ['Status', 'Staged', 'Commit Hash', 'Message']
    commits = [('a' * 40, 'Merge bitcoin/bitcoin#123: example'),
               ('b' * 40, 'Merge bitcoin-core/gui#456: example')]

    def test_append_only_preserves_annotations_and_is_idempotent(self):
        rows = [self.header, ['DNM (Did Not Merge)', 'Staged', 'a' * 10, 'message', 'manual note']]
        original = [r[:] for r in rows]
        additions = sync.missing_rows(rows, self.commits)
        self.assertEqual(rows, original)
        self.assertEqual(additions, [['', '', 'b' * 10, self.commits[1][1], '', '', '', '', '', '']])
        self.assertEqual(sync.missing_rows(rows + additions, self.commits), [])

    def test_reject_bad_or_duplicate_commits(self):
        for hashes in [['c' * 10], ['a' * 10, 'a' * 10], ['a']]:
            with self.subTest(hashes=hashes), self.assertRaises(ValueError):
                sync.missing_rows([self.header] + [['', '', sha] for sha in hashes], self.commits)

    def test_pr_merge_filter(self):
        for subject in [c[1] for c in self.commits] + ['Merge #789: example']:
            self.assertTrue(sync.PR_MERGE.match(subject))
        for subject in ['Update leveldb subtree', "Merge commit 'abc' into subtree"]:
            self.assertFalse(sync.PR_MERGE.match(subject))

    def test_upcoming_range_uses_pinned_master_only_without_tag(self):
        for tag_exists, expected in [(0, 'v33.0'), (1, 'master')]:
            with self.subTest(tag_exists=tag_exists), \
                 patch.object(sync.subprocess, 'run', return_value=MagicMock(returncode=tag_exists)), \
                 patch.object(sync, 'git_output', side_effect=['a' * 40, 'b' * 40, '']) as output:
                result = sync.upstream_merges('repo', 'v32.0', 'v33.0')
                self.assertEqual(result[2], expected)
                self.assertEqual(output.call_args_list[1].args[-1], expected + '^{commit}')
                self.assertEqual(output.call_args_list[2].args[-1], 'a' * 40 + '..' + 'b' * 40)

    def test_sync_defaults_to_audit(self):
        spreadsheet = MagicMock()
        worksheet = spreadsheet.worksheet.return_value
        worksheet.get_all_values.return_value = [self.header]
        with patch.object(sync, 'VERSION_RANGES', {'v33': ('v32.0', 'v33.0')}), \
             patch.object(sync, 'upstream_merges', return_value=('a', 'b', 'master', self.commits)), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(sync.sync_tabs(spreadsheet, 'repo'), 2)
            worksheet.append_rows.assert_not_called()
            sync.sync_tabs(spreadsheet, 'repo', apply=True)
            worksheet.append_rows.assert_called_once()

    def test_invalid_later_tab_prevents_all_writes(self):
        spreadsheet = MagicMock()
        first, second = MagicMock(), MagicMock()
        spreadsheet.worksheet.side_effect = [first, second]
        first.get_all_values.return_value = [self.header]
        second.get_all_values.return_value = [self.header, ['', '', 'c' * 10]]
        with patch.object(sync, 'VERSION_RANGES', {'v32': ('v31.0', 'v32.0'), 'v33': ('v32.0', 'v33.0')}), \
             patch.object(sync, 'upstream_merges', return_value=('a', 'b', 'master', self.commits)), \
             redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
            sync.sync_tabs(spreadsheet, 'repo', apply=True)
        first.append_rows.assert_not_called()
        second.append_rows.assert_not_called()

    def test_concurrent_edit_prevents_append(self):
        spreadsheet = MagicMock()
        worksheet = spreadsheet.worksheet.return_value
        worksheet.get_all_values.side_effect = [[self.header], [self.header, ['', '', '', '', 'new note']]]
        with patch.object(sync, 'VERSION_RANGES', {'v33': ('v32.0', 'v33.0')}), \
             patch.object(sync, 'upstream_merges', return_value=('a', 'b', 'master', self.commits)), \
             redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
            sync.sync_tabs(spreadsheet, 'repo', apply=True)
        worksheet.append_rows.assert_not_called()


if __name__ == '__main__':
    unittest.main()
