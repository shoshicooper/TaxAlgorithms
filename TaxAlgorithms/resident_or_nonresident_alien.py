"""
(c) 2022 Shoshi (Sharon) Cooper.  No duplication is permitted for commercial use.  Any significant changes made must be
stated explicitly and the original source code, if used, must be available and credited to Shoshi (Sharon) Cooper.

Determines if a taxpayer is a resident or a nonresident alien.
See Reg 301.7701(b)-1
"""
from enum import Enum, auto
from TaxAlgorithms.dependencies_for_programs.date_funcs import *


class AlienType(Enum):
    RESIDENT = auto()
    NONRESIDENT = auto()


class DaysInCountry(object):
    """
    Keeps track of days in a Country (US) by looking at when passport says you arrived and left.

    What does NOT count as a day in the US/Country:
        - days in the US for less than 24 hours as a stopover from country A to country B
        - days in US as crew member of foreign vessel
        - days you are unable to leave US due to medical condition that develops while you are in US
        - days you commute to work in US from a residence in Canada or Mexico if the commute is regular

    This class does NOT check for these conditions, so keep them in mind while adding.
    """
    RATIOS = [1, 1/3, 1/6]

    def __init__(self, country_arrivals=(), country_departures=()):
        """Lists in us_arrivals and us_departures should be lists of Date class objects"""
        self._arrivals = []
        self._departures = []

        # Add arrivals and departures passed through in init
        for arrival in country_arrivals:
            self.add_arrival(arrival)
        for departure in country_departures:
            self.add_departure(departure)

    def add_arrival(self, date_arrived):
        self._add_date(self._arrivals, date_arrived)

    def add_departure(self, date_departed):
        self._add_date(self._departures, date_departed)

    def _add_date(self, lst, date):
        self._date_type_check(date)
        i = self._find_insertion_index(lst, date)
        lst.insert(i, date)

    def days_in_us(self, start_date=None, end_date=None):
        return self.days_in_country(start_date, end_date)

    def days_in_country(self, start_date=None, end_date=None):
        """Number of days spent inside the United States during a particular period"""
        if len(self._arrivals) == 0 and len(self._departures) == 0:
            return 0

        start_date = self._arrivals[0] if start_date is None else start_date
        end_date = max(self._arrivals[-1], self._departures[-1]) if end_date is None else end_date

        days = 0
        for i in range(len(self._arrivals)):
            if self._arrivals[i] < start_date:
                continue
            elif self._arrivals[i] > end_date:
                break

            arrived = self._arrivals[i]

            j = i
            try:
                while self._departures[j] < arrived:
                    j += 1
                left = self._departures[j] if self._departures[j] < end_date else end_date
            except IndexError:
                left = end_date

            days += days_between(left, arrived)

        return days

    def weighted_days_in_us(self, end_date):
        """Weighted by the standards that the IRS has set out"""
        # Calculate starts and ends of years
        prior_year = back_one_year(end_date)
        year_before = back_one_year(prior_year)
        two_years_ago = back_one_year(year_before)

        # Find out days during each of those years
        current_year_days = self.days_in_us(start_date=prior_year, end_date=end_date)
        cy_minus_1y = self.days_in_us(start_date=year_before, end_date=prior_year)
        cy_minus_2y = self.days_in_us(start_date=two_years_ago, end_date=year_before)

        # These must be weighted according to the IRS rules
        weighted_days = 0
        for i, num_days in enumerate([current_year_days, cy_minus_1y, cy_minus_2y]):
            weighted_days += self.RATIOS[i] * num_days

        return weighted_days


    def is_twelve_month_period(self, end_date):
        """
        This is for the foreign earned income exclusion.  It uses the same mechanic and should use the same object,
        but tests something different.

        This tests to see if you were physically present for 330 days in any 12-month period.

        For the sake of this particular test, the "Country" should be the country you are claiming residence in,
        which is NOT the US.
        """

        # TODO: This is an extremely slow way to do this.  I believe a graph could help solve this faster.

        if not self._departures:
            date = self._arrivals[0]
        else:
            date = min(self._arrivals[0], self._departures[0])

        while date < end_date:
            num_days = self.days_in_country(date, date.add_one_year())
            if num_days >= 330:
                return True
            date = date + 1

        return False

    @staticmethod
    def _date_type_check(date):
        """I will ducktype this, because I really just need to make sure that these three attributes are here"""
        day, month, year = date.day, date.month, date.year

    @staticmethod
    def _find_insertion_index(lst, new_obj, end: int = None, key=lambda x: x):
        """Borrowed from my BinaryInsertSort Repository (code unmodified, but comments cut out)"""
        start = 0
        if end is None:
            end = len(lst) - 1

        while True:
            if end < 0 or start > end:
                return start

            middle = (end + start) // 2

            if middle > 0 and key(lst[middle - 1]) < key(new_obj) < key(lst[middle]) or key(lst[middle]) == key(
                    new_obj):
                return middle

            elif key(new_obj) < key(lst[middle]):
                end = middle - 1
            else:
                start = middle + 1


def get_alien_type(tax_year_end, days_in_us: DaysInCountry, green_card_start_date=None):
    """Determines if a non-US citizen is a resident or nonresident alien"""
    # Green card test: if taxpayer is a lawful permanent resident of us at any time during the year, then pass
    if green_card_start_date is not None and green_card_start_date <= tax_year_end:
        return AlienType.RESIDENT

    # Tax year end is an inclusive year end, so I must make it exclusive to work with the algorithms
    exclusive_year_end = timestamp_to_date(make_timestamp(tax_year_end) + 24 * 60 * 60)
    year_start = back_one_year(exclusive_year_end)

    # Substantial Presence Test:
    #   1) Has the person been in the US for 31 days (or more) in THIS tax year?
    #   2) has the person been in the US for 183 weighted days (or more) in the PAST 3 tax years?
    # Must meet both to qualify.
    current_year_days_in_us = days_in_us.days_in_us(start_date=year_start, end_date=exclusive_year_end)
    if current_year_days_in_us < 31:
        return AlienType.NONRESIDENT
    if days_in_us.weighted_days_in_us(exclusive_year_end) < 183:
        return AlienType.NONRESIDENT

    # How I did the Substantial presence test:
    #   Take the ratios from DaysInUS.  They pertain to the following time periods: [this_year, last_year, year_before]
    #   So in essence, we have two lists that have equivalent dimensions:
    #      days_in_us_during_year = [year2020, year2019, year2018]
    #      ratios_per_year =        [1,        1 / 3,    1 / 6]
    #   You can see how they line up.
    #   At this point, we are simply weighting the days list by the years list:
    #
    #   for(i = 0; i < ratios.size(); i++){
    #       weighted_days += ratios[i] * days_in_us_during_year[i]
    #   }
    #
    #   FAILURE CONDITION: year2020 days < 31 or weighted_days < 183
    #   else: Substantial presence test passes

    return AlienType.RESIDENT












