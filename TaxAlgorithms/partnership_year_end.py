"""
(c) 2022 Shoshi (Sharon) Cooper.  No duplication is permitted for commercial use.  Any significant changes made must be
stated explicitly and the original source code, if used, must be available and credited to Shoshi (Sharon) Cooper.

Finds the required year-end for a partnership.
Note that the Least Aggregate Deferral computation is a simple matrix dot product.
"""
import datetime
import numpy as np
from TaxAlgorithms.dependencies_for_programs.date_funcs import days_between


def find_partnership_tax_year_end(partners, current_year_end=datetime.date(2020, 12, 31)):
    """
    Finds the year end from the partners.

    The first two steps are self-explanatory and taken from IRC §706 and CFR § 1.706-1.

    The last step (Least Aggregate Deferral) is more interesting:
    The key to doing this is to realize that the process of finding the partnership year end is a dot product.
    What's more, it's actually taking a 2D matrix of inputs and multiplying it by a 1D array of weights.

    This process should sound extremely familiar to those with a computer science background.
    """
    YEAR_END = 0
    PSHIP_INTEREST = 1
    cye = None if current_year_end is None else (current_year_end.month, current_year_end.day)
    index = None

    # First, grab all the year ends
    year_ends = {}
    possible_ends_over_5_percent = set()

    for i, partner in enumerate(partners):
        year_ends.setdefault(partner.year_end, []).append(partner)
        if partner.capital_interest >= .05 or partner.profit_interest >= .05:
            possible_ends_over_5_percent.add(partner.year_end)
        # Keep track of this for the deminimus rule at the end
        if (partner.year_end.month, partner.year_end.day) == cye:
            index = i

    # 1) Majority partner rule: if more than 50% of the owners of the partnership
    #    (capital and profits) have the same year end, you use that year end
    for end_date, partners_with_enddate in year_ends.items():
        total_ownership_capital = sum([x.capital_interest for x in partners_with_enddate])
        total_ownership_profit = sum([x.profit_interest for x in partners_with_enddate])

        if total_ownership_capital > .5 and total_ownership_profit > .5:
            return end_date

    # 2) Principal partner test: all partners that own 5% or more of capital OR profits.
    #    If all of those have the same year end, use that year end
    if len(possible_ends_over_5_percent) == 1:
        return possible_ends_over_5_percent.pop()

    # 3) Least aggregate deferral
    #    Looks at all possible year ends and tests the partners using a weighted average approach to see
    #    which will give the least deferral

    # Step 3 is to create a 2D matrix of ((test_years - each_year) // 30), then find the dot product of
    # that and the partnership interest.  Find the min of your dot product and return the year associated with it.
    info = compile_attributes(partners, ['year_end', 'profit_interest'])
    matrix = create_matrix(info[YEAR_END])
    deferral_periods = matrix.dot(info[PSHIP_INTEREST])
    # If there's a tie, then you can use either -- unless your partnership currently has that particular
    # year end.  Then you must stick with the one you have.  See CFR 1.706-1 Example 3
    min_deferral = deferral_periods.min()
    end_dates = set(info[YEAR_END, x] for x in range(len(deferral_periods)) if deferral_periods[x] == min_deferral)
    if len(end_dates) > 1:
        all_year_ends = set([(x.month, x.day) for x in end_dates])
        if cye in all_year_ends:
            return current_year_end
        return end_dates
    # Special de minimus rule CFR 1.706-1(b)(iii)
    if current_year_end is not None and index is not None:
        deferral_for_current = deferral_periods[index]
        if deferral_for_current - deferral_periods.min() < .5:
            return current_year_end

    # np.argmin gives you the index where the min value is located in the array
    return info[YEAR_END, np.argmin(deferral_periods)]


def create_matrix(each_year):
    """Creates a matrix that broadcasts out test_years on one axis and year_ends on the other"""
    test_years = np.array([HalfDate.from_date(x) for x in each_year])
    each_year = each_year[:, np.newaxis]

    # The formula to combine these into a matrix!!!!
    return (test_years - each_year) // 30



class HalfDate(datetime.date):
    """
    This date can switch its year based on what it's being compared to.
    This is required for the Least Aggregate Deferral Method in selecting a partnership date
    """

    @classmethod
    def from_date(cls, date):
        return cls(month=date.month, day=date.day, year=date.year)

    def __sub__(self, other):
        """
        Assumes we're doing test_date - other_date.
        I will only do this direction because in the other direction, I want it not to switch.
        """
        if isinstance(other, datetime.date) and self.month < other.month:
            me = datetime.date(month=self.month, day=self.day, year=self.year + 1)
            return days_between(me, other)
        return days_between(self, other)


def compile_attributes(lst, attributes_to_compile):
    arr = None
    for attribute in attributes_to_compile:
        row = np.array([getattr(x, attribute) for x in lst])
        arr = np.vstack((arr, row)) if arr is not None else row
    return arr


