"""
(c) 2022 Shoshi (Sharon) Cooper.  No duplication is permitted for commercial use.  Any significant changes made must be
stated explicitly and the original source code, if used, must be available and credited to Shoshi (Sharon) Cooper.
"""

# Federal tax brackets
import json
from dependencies_for_programs.filing_status_enum import FilingStatus


class TaxBracket(object):
    by_filing_status = {}
    current_year = None

    class BracketLimit(object):
        def __init__(self, start, end, rate_tuple, str_of_lambda):
            self._start = start
            self._end = end
            # rate should be a tuple
            self._rate = rate_tuple
            self._str_of_lambda = str_of_lambda

        def __call__(self, amount):
            return self.rate_lambda(amount)

        @property
        def lower(self):
            return self._start

        @property
        def upper(self):
            return self._end

        def rate_lambda(self, taxable_income):
            return self.rate_func(taxable_income, *self._rate)

        @staticmethod
        def rate_func(taxable_amount, plus_col, rate_col, amount_over_col):
            amount_over = taxable_amount - amount_over_col
            tax_rt = rate_col * amount_over
            total = plus_col + tax_rt
            return total

        def __contains__(self, item):
            lower = self.lower[0] if isinstance(self.lower, tuple) else self.lower
            upper = self.upper[0] if isinstance(self.upper, tuple) else self.upper
            return lower <= item < upper

        def __str__(self):
            lower = self.lower[0] if isinstance(self.lower, tuple) else self.lower
            upper = self.upper[0] if isinstance(self.upper, tuple) else self.upper
            return f"<{lower} to {upper}: {self._str_of_lambda}>"



    def __init__(self, year, filing_status, bracket_list):
        self._year: int = year
        self._filing_status: FilingStatus = filing_status
        self._brackets_by_lower_limit = dict(*[x for x, y, z in bracket_list])
        self._intro_bcktlist(bracket_list)

    def __call__(self, taxable_income, ordinary_income=None):
        if ordinary_income is None:
            ordinary_income = taxable_income

        bracket = self[taxable_income]
        return bracket(ordinary_income)

    def _intro_bcktlist(self, bracket_list):
        for i in range(len(bracket_list)):
            lower, rate, rate_str = bracket_list[i]
            upper = float("inf") if len(bracket_list) == i + 1 else bracket_list[i + 1]

            self._brackets_by_lower_limit[lower] = self.BracketLimit(lower, upper, rate, rate_str)

    @property
    def year(self):
        return self._year

    @property
    def filing_status(self):
        return self._filing_status

    def __getitem__(self, amount):
        """Looks up amount to see which tax bracket it falls into"""
        for lower_lim, bracket in self._brackets_by_lower_limit.items():
            if amount in bracket:
                return bracket

    @staticmethod
    def make_lambda(plus_col, rate_col, amount_over_col):
        rates = []
        rate_strings = []
        for i in range(len(rate_col)):
            rates.append((plus_col[i], rate_col[i], amount_over_col[i]))
            rate_strings.append(f"lambda x: {plus_col[i]} + {rate_col[i]} * (x - {amount_over_col[i]})")
        return rates, rate_strings


    @classmethod
    def load_year(cls, year):
        """loads a particular year from the tax tables"""
        cls.by_filing_status.clear()
        cls.current_year = year

        with open('../yearly_constants/tax_tables/tax_worksheets.json') as file:
            j_table = json.load(file)

        year_data = j_table[str(year)]
        for bracket, data in year_data.items():
            enm = FilingStatus[bracket.upper()]
            rate, rate_str = cls.make_lambda(data['plus_column'], data['rates'], data['of_amount_over'])
            bundled = list(zip(data['lower_limit'], rate, rate_str))
            cls.by_filing_status[enm] = TaxBracket(year, enm, bundled)

    @classmethod
    def get(cls, filing_status, year=None):
        year = year or cls.current_year
        if isinstance(filing_status, str):
            filing_status = FilingStatus[filing_status.upper()]

        if year != cls.current_year:
            cls.load_year(year)
        return cls.by_filing_status[filing_status]


