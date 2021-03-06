import csv
import os
import sys
from dataclasses import dataclass
from enum import Enum
import requests
import git
from multiprocessing import Pool
from datetime import date

document_id = "1DnKxat0S0H62CJOzXpKGPXTa8hgoVOjGYZzoClmGSB8"


def download_and_write_file(file_tuple):
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


repo = git.Repo
if not os.path.isdir("dashpaydash"):
    print("Cloning dashpay/dash repo")
    repo = git.Repo.clone_from('https://github.com/dashpay/dash', 'dashpaydash', branch='develop')
    print("Done cloning repo")
else:
    print("Initializing dashpay/dash repo")
    repo = git.Repo('dashpaydash')
    repo.git.checkout("develop")

assert str(repo.head.reference) == "develop"
repo.remotes.origin.pull()

files = [
    ('0.16.csv', "1860904166"),
    ('0.17.csv', "119635402"),
    ('0.18.csv', "988587662"),
    ('0.19.csv', "259176943"),
    ('0.20.csv', "1507625552"),
    ('0.21.csv', "331846632"),
    ('0.22.csv', "1796444839")
]

download_sheet_as_csv(files)


class StatusDone(Enum):
    DONE = 1
    DNM = 2
    NONE = 3


class StatusStaged(Enum):
    STAGED = 1
    NONE = 2


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
        ret = self.version + " "
        if self.status_done is StatusDone.DONE:
            ret += "DONE "
        elif self.status_done is StatusDone.DNM:
            ret += "DNM "
        elif self.status_staged is StatusStaged.STAGED:
            ret += "STAGED "
        else:
            ret += "NOT_STAGED "

        ret += self.commit_hash + " " + self.message + " " + self.notes + " " + str(self.problem)
        return ret


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
            except IndexError:
                obj.non_trivial = True

            backport_objects.append(obj)

commit = repo.head.reference.commit

print("Commit hash:", commit)

log = []
log_temp = repo.git.log("--oneline").split("\n")

# This will filter off the commit id, and everything after first semicolon
for v in log_temp:
    # if not ("Merge" in v or "merge" in v or "bitcoin" in v or "Backport" in v or "backport" in v): continue
    log.append(v.split(" ", 1)[1].lower())

print(len(log))


def search_for_merge_number(log_i, backport_object, ignore_partial=True):
    number = backport_object.get_number()
    for item in log_i:
        item = item.lower()

        if "bitcoin-core/gui" in item and "bitcoin-core/gui" not in backport_object.message:
            continue

        if ("bitcoin #" + number) in item or ("bitcoin#" + number) in item or ("merge #" + number) in item or \
                ("backport " + number) in item or ("backport #" + number) in item \
                or ("merge: #" + number) in item or ("bitcoin " + number) in item:
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
]

def check_object(obj):
    if obj.commit_hash in ignore_list:
        return True

    if "Merge #" not in obj.message:
        return True

    if obj.status_done is StatusDone.DONE:
        if not search_for_merge_number(log, obj):
            print("Stated done, not found for: ", obj.get_number())
            return False
    else:
        if search_for_merge_number(log, obj):
            print("Stated NOT done, found for:", obj.get_number())
            return False
    return True


with Pool(8) as pool:
    results = pool.map(check_object, backport_objects)

if False in results:
    print("Errors detected!")
    sys.exit(1)
else:
    print("All good, no errors detected.")

