"""
(c) 2022 Shoshi (Sharon) Cooper.  No duplication is permitted for commercial use.  Any significant changes made must be
stated explicitly and the original source code, if used, must be available and credited to Shoshi (Sharon) Cooper

Objects that represent an amount that is being limited in some way.

The idea is to use these objects to make it much easier to understand what's going on conceptually.
Example: You can only take 3000 deduction in capital loss
    cap_loss = LimitedAmount(upper_limit=3000, start=abs(net_capital_loss))
    rollover = cap_loss.excess

Note: It'd read better if the start parameter was a non-keyword parameter in position 0, so it'd be:
    LimitedAmount(100_000, upper_limit=10_000)
        where 100_000 is the amount we are limiting.

    But that currently doesn't work with the code I have, since I often make empty LimitedAmount objects that
    only contain the limit and the starting amount is 0.  Then I add to the object over time.
"""


class LimitedAmount(object):
    """Limits the amount that you can go up to"""

    def __init__(self, upper_limit, start=0, funcs_to_perform=(), **kwargs):
        self._limit = upper_limit
        self._excess = 0
        for func in funcs_to_perform:
            func()
        self._amount = start


    def __iadd__(self, other):
        """Adds two numbers together, but not past the limit.  Must do it this way so negative numbers work"""
        if isinstance(other, LimitedAmount):
            return self._amount + other._amount
        bulk_amount = self._amount + self._excess + other

        if bulk_amount > self._limit:
            self._excess = max(0, bulk_amount - self._limit)
            self._amount = self.limit
        else:
            self._amount = bulk_amount
            self._excess = 0
        return self

    def __radd__(self, other):
        return self + other

    def __add__(self, other):
        limited = self.copy()
        limited += other
        return limited

    def __isub__(self, other):
        self.__iadd__(-other)
        return self

    @property
    def excess(self):
        return self._excess

    @property
    def limit(self):
        return self._limit


    def how_much_used(self, total):
        """
        Tries to increase the amount, then sees how much could be used.
        The amount actually used is then returned.
        """
        original = self._amount
        self.__iadd__(total)
        later = self._amount
        return later - original

    def copy(self):
        new = type(self)(self.limit, self._amount)
        new._excess = self._excess
        return new

    @classmethod
    def transfer(cls, other):
        new = cls(other.limit)
        for attr_name, attr_val in vars(other).items():
            setattr(new, attr_name, attr_val)
        return new

    @property
    def amount(self):
        return self._amount




class DoubleLimitedAmount(LimitedAmount):
    """An amount that has both an upper and a lower cap"""

    def __init__(self, lower_limit, upper_limit, start=0, **kwargs):
        super().__init__(upper_limit=upper_limit, start=0, funcs_to_perform=[], **kwargs)
        self._lower_limit = lower_limit
        self._suspended = 0

        # Must now introduce everything using the correct lower limits
        self.__iadd__(start)

    @property
    def _lower_limit(self):
        try:
            return self.__lower_limit
        except AttributeError:
            return 0

    @_lower_limit.setter
    def _lower_limit(self, value):
        if value > self.limit:
            raise ValueError("Must be less than upper limit")
        self.__lower_limit = value

    @property
    def lower_limit(self):
        return self.__lower_limit

    @property
    def _suspended(self):
        try:
            return self.__suspended
        except AttributeError:
            return 0

    @_suspended.setter
    def _suspended(self, value):
        if value > self._lower_limit:
            raise ValueError("Cannot suspend amount larger than lower limit")
        self.__suspended = value



    def _suspend(self):
        """To suspend the amount because it's less than the lower limit"""
        if self._amount > self._lower_limit:
            raise ValueError("Should not suspend! Lower limit has been met")
        self._suspended = self._amount
        self._amount = 0

    def _unsuspend(self):
        """To unsuspend the amount because we are about to use it"""
        self._amount = self._suspended
        self._suspended = 0

    def __iadd__(self, other):
        if self._amount == 0 and self._suspended > 0:
            self._unsuspend()
        super().__iadd__(other)
        bulk_amount = self._amount + self._excess
        if bulk_amount < self._lower_limit:
            self._suspend()
        elif self._amount < self._lower_limit:
            excess = self._excess
            self._excess = 0
            self.__iadd__(excess)
        return self

    def copy(self):
        new = type(self)(self._lower_limit, self.limit, self._amount)
        new._excess = self._excess
        new._suspended = self._suspended
        return new

    def __isub__(self, other):
        return self.__iadd__(-other)

    def __sub__(self, other):
        return self.__add__(-other)


class DoubleBoundedAmount(DoubleLimitedAmount):
    """
    Similar to DoubleLimitedAmount, except that the limit is returned if it's below the lower limit.
    In DoubleLimitedAmount, by contrast, the entire amount is suspended if it's below the lower limit
    (which is what's done with most deductions and credits that have two limits, but not standard deductions).
    """


    def __iadd__(self, other):
        super().__iadd__(other)
        bulk_amount = self._amount + self._excess
        if bulk_amount < self._lower_limit:
            self._excess += -(self._lower_limit - bulk_amount)
            self._amount = self._lower_limit
        elif self._amount < self._lower_limit:
            excess = self._excess
            self._excess = 0
            self.__iadd__(excess)
        return self

    @property
    def amount(self):
        return self._amount



class LimitedExpense(LimitedAmount):
    """An expense that can only go up to a certain limit and then is capped"""

    @property
    def expense(self):
        return self.amount

    def take_deduction(self, total_expense):
        """
        Takes a deduction and returns the amount of the deduction that was able to be taken
        with consideration to the limit.
        """
        original_expense = self.expense
        self.__iadd__(total_expense)
        later_expense = self.expense
        return later_expense - original_expense



