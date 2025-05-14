#!/usr/bin/env python3

import csv
import os
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from functools import partial
from pprint import pprint

import requests
import git
from multiprocessing import Pool
from datetime import date


import argparse

# Google Sheets integration
import gspread
from oauth2client.service_account import ServiceAccountCredentials

DOCUMENT_ID = "1DnKxat0S0H62CJOzXpKGPXTa8hgoVOjGYZzoClmGSB8"


def download_and_write_file(file_tuple):
    document_id = "1DnKxat0S0H62CJOzXpKGPXTa8hgoVOjGYZzoClmGSB8"

    file = file_tuple[0]
    gid = file_tuple[1]
    print("downloading", file)
    file_link = f"https://docs.google.com/spreadsheets/d/{document_id}/export?gid={gid}&format=csv"
    response = requests.get(file_link)
    assert response.status_code == 200, 'Wrong status code'

    if os.path.exists(file):
        os.remove(file)

    with open(file, "wb") as csvfile:
        csvfile.write(response.content)


def download_sheet_as_csv(files):
    print("downloading necessary google sheet files")
    with Pool(len(files)) as p:
        p.map(download_and_write_file, files)

    return


class StatusDone(Enum):
    DONE = 1
    DNM = 2
    NONE = 3

    def __str__(self):
        if self == StatusDone.DONE:
            return "DONE"
        elif self == StatusDone.DNM:
            return "DNM"
        elif self == StatusDone.NONE:
            return "NONE"
        assert False



class StatusStaged(Enum):
    STAGED = 1
    NONE = 2
    def __str__(self):
        if self == StatusStaged.STAGED:
            return "STAGED"
        elif self == StatusStaged.NONE:
            return "NONE"
        assert False


@dataclass
class backport_object:
    status_done: StatusDone
    status_staged: StatusStaged
    commit_hash: str
    message: str
    notes: str
    problem: bool
    version: str
    non_trivial: bool

    def get_number(self):
        return self.message.split("#", 1)[1].split(":", 1)[0]

    def __str__(self):
        ret = f"{self.version} {self.status_done} {self.status_staged} {self.commit_hash} {self.message} {self.notes} {str(self.problem)}"
        return ret


def search_for_merge_number(log_i, backport_object, ignore_partial=True):
    number = backport_object.get_number()
    is_gui = "bitcoin-core/gui" in backport_object.message
    for item in log_i:
        item = item.lower()

        if not is_gui:
            if ("bitcoin #" + number) in item or ("bitcoin#" + number) in item or ("merge #" + number) in item or \
                    ("backport " + number) in item or ("backport #" + number) in item \
                    or ("merge: #" + number) in item or ("bitcoin " + number) in item:
                if ignore_partial and "partial" in item:
                    continue
                return True
        else:
            if f"gui#{number}:" in item:
                if ignore_partial and "partial" in item:
                    continue
                return True

    return False


ignore_list = [
    "d451d0bcf",
    "e7f125562",
    "6970b30c6",
    "46d1ebfcf",
    "0f8e09599",
    "aae64a21b",
    "9a75902c5",
    "9a2db3b3d",
    "5f0c6a7b0",
    "e76acf338",
    "418ae49ee",
    "d9ebb6391",
    "5c05dd628",
    "19d8ca5cc",
    "cbb91cd0e",

    # Needed as these are ambiguous ex: "Merge #20" is ambiguous and results in false positives
    "9453fbf5a0",
    "d875bcc8f9",
    "d1ddead09a",
    "7fca189a2a",
    "7723479300",
    "03ecceedf6",
]


def check_object(log, obj):

    if obj.commit_hash in ignore_list:
        return True

    if "Merge " not in obj.message and "merge" not in obj.message:
        return True

    if obj.status_done is StatusDone.DONE:
        if not search_for_merge_number(log, obj):
            print("Stated done, not found for: ", obj.message.split('`')[0])
            return False
    else:
        if search_for_merge_number(log, obj):
            print("Stated NOT done, found for:", obj.message.split('`')[0])
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Backports validation script")
    parser.add_argument('--count', type=int, default=0, help='Number of PRs to backport')
    parser.add_argument('--check-only', action='store_true', help='Only run checks, do not backport any PRs')
    args = parser.parse_args()
    # Initialize Google Sheets client
    scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name('.secrets/service_account.json', scope)
    gs_client = gspread.authorize(creds)
    spreadsheet = gs_client.open_by_key(DOCUMENT_ID)
    log = []
    if not os.path.isdir("dashpaydash"):
        print("Cloning dashpay/dash repo")
        try:
            repo = git.Repo.clone_from('https://github.com/dashpay/dash', 'dashpaydash', branch='develop')
            repo.create_remote('bitcoin', 'https://github.com/bitcoin/bitcoin')
            repo.remote('bitcoin').fetch()
            print("Done cloning repo")
        except git.exc.GitCommandError as e:
            print(f"Error cloning repository: {e}")
            sys.exit(1)
    else:
        print("Initializing dashpay/dash repo")
        try:
            repo = git.Repo('dashpaydash')
            repo.git.checkout("develop")
            repo.remotes.origin.pull('develop')
        except git.exc.GitCommandError as e:
            print(f"Error initializing repository: {e}")
            sys.exit(1)

    files = [
        ('0.16.csv', "1860904166"),
        ('0.17.csv', "119635402"),
        ('0.18.csv', "988587662"),
        ('0.19.csv', "259176943"),
        ('0.20.csv', "1507625552"),
        ('0.21.csv', "331846632"),
        ('0.22.csv', "1796444839"),
        ('0.23.csv', "1637681185"),
        ('0.24.csv', "1723848108"),
        ('0.25.csv', "1543943941"),
        ('0.26.csv', "1508745094"),
        ('0.27.csv', "1591965303"),
        ('0.28.csv', "1290127568"),
    ]

    download_sheet_as_csv(files)

    backport_objects = []

    for file, _ in files:
        with open(file) as csvfile:
            reader = csv.reader(csvfile, delimiter=',')
            line = 0
            for row in reader:
                line += 1

                if row[0] == "Status":
                    continue

                # Skip fully blank lines
                if row[0] == "" and row[1] == "" and row[2] == "" and row[3] == "":
                    continue

                obj = backport_object(StatusDone.NONE, StatusStaged.NONE, "", "", "", False, csvfile.name, False)
                if row[0] == "DNM (Did Not Merge)":
                    obj.status_done = StatusDone.DNM
                elif row[0] == "Done (Merged to dashpay)":
                    obj.status_done = StatusDone.DONE

                if "Staged" in row[1]:
                    obj.status_staged = StatusStaged.STAGED

                obj.commit_hash = row[2]
                obj.message = row[3]

                try:
                    obj.non_trivial = row[9] == 'TRUE'
                    assert row[9] == 'TRUE' or row[9] == 'FALSE'
                except IndexError:
                    obj.non_trivial = True
                try:
                    obj.get_number()
                    backport_objects.append(obj)
                except:
                    pass


    commit = repo.head.reference.commit

    print("Commit hash:", commit)

    log_temp = repo.git.log("--oneline").split("\n")

    # This will filter off the commit id, and everything after first semicolon
    for v in log_temp:
        log.append(v.split(" ", 1)[1].lower())

    print(len(log))

    with Pool(8) as pool:
        results = pool.map(partial(check_object, log), backport_objects)
    # pprint(results)
    # Single threaded version to use when debugging
    # results = []
    # for obj in backport_objects:
    #     results.append(check_object(obj))

    to_backport_count = args.count

    if False in results:
        print("Errors detected!")
    else:
        print("All good, no errors detected.")
        if args.check_only:
            print("Check-only mode enabled; skipping backporting.")
            sys.exit(0)
    # Batch update any rows that were incorrectly marked NOT done but actually merged
    for obj, passed in zip(backport_objects, results):
        if not passed and obj.status_done is not StatusDone.DONE and search_for_merge_number(log, obj):
            sheet_name = obj.version.replace('.csv', '')
            try:
                worksheet = spreadsheet.worksheet(sheet_name)
                cell = worksheet.find(obj.message)
                row = cell.row
                worksheet.update_cell(row, 1, "Done (Merged to dashpay)")
                worksheet.update_cell(row, 2, "")
                worksheet.update_cell(row, 7, "")
                print(f"Updated sheet '{sheet_name}' row {row} for {obj.message}")
            except Exception as e:
                print(f"Failed to update sheet '{sheet_name}' for {obj.message}: {e}")

    if repo.is_dirty():
        try:
            repo.git.cherry_pick("--abort")
        except git.exc.GitCommandError:
            pass
        repo.git.reset('--hard')

    try:
        repo.git.checkout("-b", f'develop-trivial-{date.today()}')
    except git.exc.GitCommandError:
        repo.git.checkout(f'develop-trivial-{date.today()}')

    backported_count = 0

    for index, obj in enumerate(backport_objects):
        if backported_count >= to_backport_count:
            print("Done :)")
            break
        if obj.status_done == StatusDone.NONE and \
                not obj.non_trivial and \
                obj.status_staged != StatusStaged.STAGED and \
                ("Merge #" in obj.message or "Merge bitcoin" in obj.message):
            try:
                repo.git.cherry_pick('-m1', f'{obj.commit_hash}')
                # To be implemented
                # build_result = subprocess.run(['cd', 'dashpaydash', '&&', 'make', '-j8'], check=True)
                print(f'(({backported_count}:{index}) / {len(backport_objects)}) {obj.commit_hash} was cherry-picked cleanly')
                backported_count += 1
            except git.exc.GitCommandError:
                repo.git.reset("--hard")
                print(f'(({backported_count}:{index}) / {len(backport_objects)}) {obj.commit_hash} NOT was cherry-picked cleanly')
            except subprocess.CalledProcessError:
                # Reset to the previous state if build fails
                repo.git.reset("--hard", "HEAD~1")
                print(f'(({backported_count}:{index}) / {len(backport_objects)}) Build failed after cherry-picking {obj.commit_hash}')

        else:
            pass
    print("Exiting...")

if __name__ == "__main__":
    main()

