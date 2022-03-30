"""
(c) 2022 Shoshi (Sharon) Cooper.  No duplication is permitted for commercial use.  Any significant changes made must be
stated explicitly and the original source code, if used, must be available and credited to Shoshi (Sharon) Cooper

This should really be a strictly typed data structure.  Later versions that I've written do this.
However, the version I created for these particular algorithms does not enforce strict typing.

This is problematic as it could lead to values not being included when they should have been included,
and the user will not realize they have been excluded.
"""


class Aggregated(list):
    """Allows for some syntactic sugar involving aggregates"""

    def __getattr__(self, attr_name):
        """If the attribute is inside the items of self, return the aggregate"""
        if attr_name == "_start_aggregation":
            return super().__getattribute__(attr_name)


        total = self.start_aggregation
        num_skips = 0
        for item in self:
            try:
                total += getattr(item, attr_name)
            except AttributeError:
                num_skips += 1

        return total

    @property
    def start_aggregation(self):
        try:
            return self._start_aggregation
        except AttributeError:
            return 0

    @start_aggregation.setter
    def start_aggregation(self, value):
        self._start_aggregation = value

