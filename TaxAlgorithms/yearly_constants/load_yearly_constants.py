"""
(c) 2022 Shoshi (Sharon) Cooper.  No duplication is permitted for commercial use.  Any significant changes made must be
stated explicitly and the original source code, if used, must be available and credited to Shoshi (Sharon) Cooper.
"""
import json


class YearConstants(object):

    def __init__(self):
        self._attrs = {}
        self._import_json()

    def _import_json(self):
        with open(f"../yearly_constants/other_yearly_constants.json") as file:
            self._attrs = json.load(file)

    def __getattr__(self, item):
        try:
            return self._attrs[item]
        except KeyError:
            return super().__getattribute__(item)

    def __getitem__(self, item):
        return self._attrs[item]


