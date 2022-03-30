"""
(c) 2022 Shoshi (Sharon) Cooper.  No duplication is permitted for commercial use.  Any significant changes made must be
stated explicitly and the original source code, if used, must be available and credited to Shoshi (Sharon) Cooper.
"""


class InvoiceOrBill(object):

    def __init__(self, invoice_number, date, amount, date_due=None, description="", category="",
                 nondeductible_portions=0):
        self._invoice_number = invoice_number
        self.date = date
        self._original_amount = amount
        self._nondeductible_portions = nondeductible_portions  # if there's part of the bill that isn't deductible
        self.due_date = date_due
        self.description = description
        self.category = category

        self._payments = []
        self._balance_due = amount

    def pay(self, date_paid, amount_paid, account_paid_from=None):
        self._payments += [(date_paid, amount_paid, account_paid_from)]
        self._balance_due -= amount_paid

    @property
    def balance(self):
        return self._balance_due

    @property
    def payments(self):
        return self._payments

    def days_late(self, current_date):
        if self.due_date is not None:
            return current_date - self.due_date
        return current_date - self.date

    @property
    def non_deductible(self):
        """returns the portion that is not deductible"""
        return self._nondeductible_portions

    @property
    def expense(self):
        """returns the total original expense"""
        return self._original_amount

    @property
    def deductible_expense(self):
        """Only the part that is deductible"""
        return self.expense - self.non_deductible

    def amount_paid_this_year(self, start_tax_year, end_tax_year):
        """For cash taxpayers: amount actually paid this year"""
        payments = 0
        for date_paid, amount_paid, account_paid_from in self._payments:
            if start_tax_year <= date_paid <= end_tax_year:
                payments += amount_paid
        return payments

    def amount_billed_this_year(self, start_tax_year, end_tax_year):
        """For accrual taxpayers: amount billed during the current tax year"""
        if start_tax_year <= self.date <= end_tax_year:
            return self._original_amount
        return 0

    @property
    def invoice_number(self):
        return self._invoice_number



class Liability(object):
    """A liability"""

    def __init__(self, amount, reason='acquisition', date_incurred=None):
        self._amount = amount
        self._reason = reason
        self._date = date_incurred
        self._interest_payments = []
        self._int_pymts = {'form_1098': [], 'not': [], 'points': []}

    @property
    def fmv(self):
        return self._amount

    @property
    def reason(self):
        return self._reason

    @property
    def date_incurred(self):
        return self._date


    def repay_principal(self, principal_amount, interest_amount=0, date=None, is_form_1098=False):
        """Repays part of the principal on the liability"""
        if principal_amount > self.fmv:
            raise ValueError("Cannot reduce a liability below it's total amount")
        self._amount -= principal_amount

        if interest_amount:
            self._interest_payments.append((date, interest_amount))

            if is_form_1098:
                self._int_pymts['form_1098'].append((date, interest_amount))
            else:
                self._int_pymts['not'].append((date, interest_amount))


    @property
    def interest_payments(self):
        return self._interest_payments

    @property
    def interest_subtypes(self):
        return self._int_pymts

    def __bool__(self):
        return bool(self.fmv)

    def __add__(self, other):
        return self.fmv + other

    def __radd__(self, other):
        return self + other

    def __sub__(self, other):
        return self.fmv - other

    def __rsub__(self, other):
        return other - self.fmv

    def __neg__(self):
        return type(self)(-self.fmv)
