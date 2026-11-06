"""Read use cases for defect editing; repositories retain all SQL statements."""
from dataclasses import dataclass
from typing import Callable

from . import domain_support, inspection_defect_repository, user_repository


@dataclass(frozen=True)
class DefectDetailReads:
    connect: Callable

    def find(self, tid):
        with self.connect() as db:
            return inspection_defect_repository.defect_by_tid(db, tid)

    def assignable_users(self):
        with self.connect() as db:
            return [dict(user) for user in user_repository.assignable_users(db)]

    def detail(self, tid):
        with self.connect() as db:
            row = inspection_defect_repository.defect_by_tid(db, tid)
            data = domain_support._defect_dict(db, row) if row else None
            users = [dict(user) for user in user_repository.assignable_users(db)] if row else []
        return row, data, users
