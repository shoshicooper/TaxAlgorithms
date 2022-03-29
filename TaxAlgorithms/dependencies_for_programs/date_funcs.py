"""
(c) 2022 Shoshi (Sharon) Cooper.  No duplication is permitted for commercial use.  Any significant changes made must be
stated explicitly and the original source code, if used, must be available and credited to Shoshi (Sharon) Cooper

Quick functions for dates.
"""
import datetime

# Year to start timestamp from
START = 1970


def days_between(date1, date2):
    """Calculates the number of days between two dates"""
    answer_in_seconds = make_timestamp(date1) - make_timestamp(date2)
    answer_in_hours = (answer_in_seconds / 60) / 60
    answer_in_days = answer_in_hours / 24
    return int(answer_in_days)


def is_a_leap_year(yyyy):
    """Checks if a year is a leap year"""
    if yyyy % 4 != 0:
        return False
    if yyyy % 100 != 0:
        return True
    return yyyy % 400 == 0


def make_timestamp(date):
    """Calculates the timestamp for any given date"""
    extra = is_a_leap_year(date.year)
    days_in_year_so_far = [0,
                           31,
                           59 + extra,
                           90 + extra,
                           120 + extra,
                           151 + extra,
                           181 + extra,
                           212 + extra,
                           243 + extra,
                           273 + extra,
                           304 + extra,
                           334 + extra]

    # Number of leap years since 1970 (or 2016)
    # I'm putting in since 2016 as an optimization, so there are fewer loops to sum up.  You can do this for any year,
    # as long as you know the number of extra days caused by leap years from 1970 to that year.
    # IMPORTANT NOTE: Omit this optimization if you are planning to timestamp from a date that is NOT 1970.
    strt_year = START
    nleapyears_from_1970_to_start = 0
    if date.year > 2016:
        strt_year = 2016
        nleapyears_from_1970_to_start = 11
    # This is the total number of leap years from 1970 to current year, which == # extra days to add due to leap years
    num_leap_years = sum([is_a_leap_year(x) for x in range(strt_year, date.year)]) + nleapyears_from_1970_to_start

    # Conversion function from days to seconds
    days_to_seconds = lambda d: ((d * 24) * 60) * 60

    # Number of days from 1/1/1970 to 1/1/current_year
    days_since_1970 = ((date.year - START) * 365) + num_leap_years

    # Convert the year, month, and day to seconds
    year_converted = days_to_seconds(days_since_1970)
    m_conv = days_to_seconds(days_in_year_so_far[date.month - 1])
    d_conv = days_to_seconds(date.day - 1)
    # Add together to get the timestamp
    return year_converted + m_conv + d_conv


def timestamp_to_date(timestamp):
    """Converts a timestamp to a date"""
    seconds_to_day = lambda secs: ((secs / 24) / 60) / 60

    num_days = seconds_to_day(timestamp) + 1
    year = START + int(num_days // 365)
    remaining_days = num_days - sum([is_a_leap_year(x) for x in range(START, year)])
    if START + num_days // 365 != year:
        year -= 1
        remaining_days += is_a_leap_year(year)
    remaining_days -= 365 * (year - START)
    if remaining_days == 0:
        return datetime.date(month=12, day=31, year=year - 1)
    elif 0 > remaining_days > -31:
        return datetime.date(month=12, day=31+remaining_days, year=year - 1)
    elif remaining_days < 0:
        year -= 1
        remaining_days += 365

    estimated_month = remaining_days // 30
    extra = is_a_leap_year(year)
    days_in_year_so_far = [0, 31, 59 + extra, 90 + extra, 120 + extra, 151 + extra, 181 + extra, 212 + extra,
                           243 + extra, 273 + extra, 304 + extra, 334 + extra, 365 + extra]
    i = int(max(estimated_month - 1, 0))

    while not(days_in_year_so_far[i] < remaining_days <= days_in_year_so_far[i + 1]):
        if days_in_year_so_far[i] > remaining_days:
            i -= 1
        elif days_in_year_so_far[i] < remaining_days:
            i += 1
        else:
            return datetime.date(month = i + 1, day=1, year=year)

    remaining_days -= days_in_year_so_far[i]
    return datetime.date(month=i + 1, day=int(remaining_days), year=year)



def get_age(date_of_birth, current_date):
    """Gets a person's age in years"""
    # Check if birthday has happened this year yet
    if current_date.month > date_of_birth.month:
        has_happened = True
    elif current_date.month < date_of_birth.month:
        has_happened = False
    elif current_date.day >= date_of_birth.day:
        has_happened = True
    else:
        has_happened = False

    # For rest of years
    num_years = days_between(datetime.date(current_date.year, 1, 1), date_of_birth) // 365
    return num_years + has_happened





def back_one_year(date, less_one_day=False, irs_round=True):
    """IRS Round will round back to the first of the month"""
    days_in_year = 365
    if less_one_day:
        days_in_year = 364
    prior_year_timestamp = make_timestamp(date) - days_in_year * 24 * 60 * 60
    prior_year = timestamp_to_date(prior_year_timestamp)
    # Which year has february 29 (if applic.)
    if date.month > 2 or (date.month == 2 and date.day == 29):
        date_with_feb = date
    else:
        date_with_feb = prior_year

    if is_a_leap_year(date_with_feb.year):
        prior_year_timestamp -= 24 * 60 * 60
        prior_year = timestamp_to_date(prior_year_timestamp)

    if irs_round and prior_year.day != 1:
        if prior_year.day < 15:
            return datetime.date(prior_year.year, prior_year.month, 1)
        else:
            while prior_year.day != 1:
                prior_year_timestamp += 24 * 60 * 60
                prior_year = timestamp_to_date(prior_year_timestamp)
    return prior_year

