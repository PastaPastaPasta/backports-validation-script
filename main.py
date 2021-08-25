import csv
import os
from dataclasses import dataclass
from enum import Enum

import git

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


files = {
    '0.16.csv',
    '0.17.csv',
    '0.18.csv',
    '0.19.csv',
    '0.20.csv',
    '0.21.csv',
    '0.22.csv'
}

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

    def __str__(self):
        ret = ""
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

# for file in files:
with open('0.17.csv') as csvfile:
    spamreader = csv.reader(csvfile, delimiter=',')
    line = 0
    for row in spamreader:
        line += 1

        if row[0] == "Status":
            continue

        # Skip fully blank lines
        if row[0] == "" and row[1] == "" and row[2] == "" and row[3] == "":
            continue

        obj = backport_object(StatusDone.NONE, StatusStaged.NONE, "", "", "", False)
        if row[0] == "DNM (Did Not Merge)":
            obj.status_done = StatusDone.DNM
        elif row[0] == "Done (Merged to dashpay)":
            obj.status_done = StatusDone.DONE

        if row[1].find("Staged"):
            obj.status_staged = StatusStaged.STAGED

        obj.commit_hash = row[2]
        obj.message = row[3]

        backport_objects.append(obj)

commit = repo.head.reference.commit

print(commit)

log = []

log_temp = repo.git.log("--oneline").split("\n")

# This will filter off the commit id, and everything after first semicolon
for v in log_temp:
    if not ("Merge" in v or "bitcoin" in v or "Backport" in v or "backport" in v): continue
    log.append(v.split(" ", 1)[1])

print(len(log))
# print(log)

def search_for_merge_number(log_i, number):
    for item in log_i:
        if ("bitcoin #" + number) in item or ("bitcoin#" + number) in item or ("Merge #" + number) in item or ("Backport " + number) in item or ("backport " + number) in item or ("bitcoin " + number) in item:
            return True
    return False

ignore_list = [
    "d451d0bcf",
    "e7f125562",
    "aae64a21b",
    "9a75902c5",
    "3de01268b",
    "9a2db3b3d",
    "5f0c6a7b0",
    "e76acf338",
    "e2746db66",
    "418ae49ee",
    "d9ebb6391",
    "5c05dd628",
    "19d8ca5cc",

]

for obj in backport_objects:

    if obj.commit_hash in ignore_list:
        continue

    if "Merge #" not in obj.message:
        continue

    number = obj.message.split("#", 1)[1].split(":", 1)[0]

    if obj.status_done is StatusDone.DONE:
        if not search_for_merge_number(log, number):
            print("Issue with", obj)

