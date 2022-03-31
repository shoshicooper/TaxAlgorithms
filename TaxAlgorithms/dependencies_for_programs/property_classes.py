"""
(c) 2022 Shoshi (Sharon) Cooper.  No duplication is permitted for commercial use.  Any significant changes made must be
stated explicitly and the original source code, if used, must be available and credited to Shoshi (Sharon) Cooper.

A bunch of different classes of property.

Some of this is a little messy.  My apologies.
"""
import collections
import enum
import functools
from abc import ABC, abstractmethod

from TaxAlgorithms.dependencies_for_programs.aggregated_list_class import Aggregated
from TaxAlgorithms.dependencies_for_programs.date_funcs import *
from TaxAlgorithms.dependencies_for_programs.invoices_bills_liabilities_etc import *
from TaxAlgorithms.dependencies_for_programs.limited_amounts import *
from TaxAlgorithms.net_capital_gains_and_losses import AllGainSale


class UseType(enum.Enum):
    PERSONAL = enum.auto()
    BUSINESS = enum.auto()
    INVESTMENT = enum.auto()
    PART_BUSINESS_PART_PERSONAL = enum.auto()


class GLCharacter(enum.Enum):
    ORDINARY = enum.auto()
    CAP_GL = enum.auto()
    SPLIT = enum.auto()


class AdjustedBasis(ABC):
    """
    Adjusted Basis object
    """
    __slots__ = ['_cost', '_cost_recovery', '_improvements', "_other_reductions", '_depreciation_taken',
                 '_sect179_taken', '_date_put_into_service', '_life', '_macrs_table']

    def __init__(self, cost, liability_assumed=0, notes_to_seller=0, unstated_interest=0, date_put_into_service=None,
                 life=5, macrs_table=None, trade_in_allowance=0):
        self._cost = cost + liability_assumed + notes_to_seller - unstated_interest
        self._cost_recovery = 0
        self._improvements = 0
        self._other_reductions = 0
        # For trade in allowance stuff
        self.cash_received = cost
        self.trade_in_allowance = trade_in_allowance

        self.depreciation_object = None

        self._depreciation_taken = {}
        self._date_put_into_service = date_put_into_service
        self._life = life
        self._macrs_table = macrs_table

    @property
    def cost_recovery(self):
        return self._cost_recovery

    @property
    def unadjusted_basis(self):
        return self._cost

    def adjusted_basis(self, **kwargs):
        section_179_and_bonus_depr = 0
        if self.depreciation_object is not None:
            section_179_and_bonus_depr = self.depreciation_object.basis_adjustments()

        return (self.unadjusted_basis + self._improvements - self._cost_recovery -
                self._other_reductions - section_179_and_bonus_depr + self.trade_in_allowance)

    @property
    def ab(self):
        return self.adjusted_basis()

    @property
    def section179_and_bonus_depr(self):
        if self.depreciation_object is None:
            return 0
        return self.depreciation_object.basis_adjustments()

    @property
    def basis_for_depr(self):
        section_179_and_bonus_depr = 0
        if self.depreciation_object is not None:
            section_179_and_bonus_depr = self.depreciation_object.basis_adjustments()
        return self.unadjusted_basis + self._improvements - self._other_reductions - section_179_and_bonus_depr

    def basis_for_depreciation(self, year):
        if self.depreciation_object:
            return self.depreciation_object.basis_for_depreciation(year=year)
        return self.basis_for_depr

    def add_improvement(self, amount):
        """To add an improvement to the property and increase AB"""
        self._improvements += amount

    def subtract_casualty_loss(self, amount_of_loss, any_amounts_for_which_no_tax_benefit_received):
        self._other_reductions += amount_of_loss - any_amounts_for_which_no_tax_benefit_received

    def subtract_other_tax_benefit(self, amount):
        self._other_reductions += amount

    def add_depreciation_object(self, obj):
        self.depreciation_object = obj
        self._life = obj.life
        self._date_put_into_service = obj.date
        self._macrs_table = obj.table

    def __getattr__(self, item):
        if item not in self.__slots__:
            return getattr(self.adjusted_basis(), item)
        return super().__getattribute__(item)

    @abstractmethod
    def depreciate(self, date):
        pass

    def __rsub__(self, other):
        return other - self.adjusted_basis()

    def __sub__(self, other):
        return self.adjusted_basis() - other

    def __add__(self, other):
        return self.adjusted_basis() + other

    def __radd__(self, other):
        return self.adjusted_basis() + other

    def __eq__(self, other):
        return self.adjusted_basis() == other

    def __str__(self):
        return str(self.adjusted_basis())

    def __repr__(self):
        return str(self)

    def __mul__(self, other):
        """If I multiply an adjusted basis by a percent, I want it to divide that adjusted basis"""
        new = type(self)(cost=self._cost * other)
        for attr_name, attr_value in vars(self).items():
            if attr_value is not None:
                setattr(new, attr_name, attr_value * other)
        return new

    def __rmul__(self, other):
        return self * other

    def __neg__(self):
        return self * -1

    @property
    def life(self):
        return self._life

    @property
    def macrs_table(self):
        return self._macrs_table

    def adjust_depreciation_expense(self, date, new_amount):
        relative_year = date.year - self._date_put_into_service.year + 1
        self._depreciation_taken[relative_year] = new_amount


class BusiInvBasis(AdjustedBasis):

    def depreciate(self, date):
        try:
            year = date.year
        except AttributeError:
            year = date
        relative_year = year - self._date_put_into_service.year + 1

        if self.depreciation_object:
            amount = self.depreciation_object.depreciation_expense(year)
        else:
            try:
                return self._depreciation_taken[relative_year]
            except KeyError:
                pass
            factor = self._macrs_table[relative_year, self._life]
            amount = factor * self._property.basis(year=year)

        self._cost_recovery += amount
        self._depreciation_taken[relative_year] = amount
        return amount


class StartupOrgBasis(BusiInvBasis):
    def depreciate(self, date):
        try:
            year = date.year
        except AttributeError:
            year = date
        relative_year = year - self._date_put_into_service.year + 1
        try:
            return self._depreciation_taken[relative_year]
        except KeyError:
            pass

        expense = self.depreciation_object.depreciation_expense(date)
        self._cost_recovery += expense
        self._depreciation_taken[relative_year] = expense
        return expense


class DepletionBasis(BusiInvBasis):
    MINERALS = enum.Enum("MINERALS",
                         "COBALT SULFUR TIN LEAD COPPER GOLD OIL GAS SHALE OIL_SHALE SILVER GRANITE LIMESTONE "
                         "POTASH MARBLE COAL SALT SODIUM_CHLORIDE GRAVEL SAND")

    @classmethod
    def _percents(cls, dictionary):
        for mineral in [cls.MINERALS.COBALT, cls.MINERALS.SULFUR, cls.MINERALS.TIN, cls.MINERALS.LEAD]:
            dictionary[mineral] = .22
        for mineral_name in "COPPER GOLD OIL GAS SHALE OIL_SHALE SILVER".split():
            dictionary[cls.MINERALS[mineral_name]] = .15
        for mineral_name in "GRANITE LIMESTONE POTASH MARBLE".split():
            dictionary[cls.MINERALS[mineral_name]] = .14
        for mineral_name in "COAL SALT SODIUM_CHLORIDE".split():
            dictionary[cls.MINERALS[mineral_name]] = .10
        for mineral_name in "GRAVEL SAND".split():
            dictionary[cls.MINERALS[mineral_name]] = .05
        return dictionary

    def __init__(self, cost, remaining_recoverable_units_in_mine, mineral_being_mined="", **kwargs):
        super().__init__(cost, **kwargs)
        self._est_recoverable_units = remaining_recoverable_units_in_mine
        self._mineral = self.MINERALS[mineral_being_mined.replace(" ", "_").upper()]
        self._accumulated_depletion = {}
        self._percent = self._percents({})

    def _cost_depletion(self, units_sold, units_mined, **kwargs):
        """
        Cost depletion (as opposed to percent depletion)
        :param date: date of tax year end
        :param units_sold: the number of units that were SOLD during current tax period
        """
        adjusted_basis = self._cost - self._cost_recovery
        depletion_per_unit = adjusted_basis / self._est_recoverable_units
        self._est_recoverable_units -= units_mined

        cost_depletion = depletion_per_unit * units_sold
        return cost_depletion

    def _percent_depletion(self, expenses, gross_income, agi=None):
        """
        :param expenses: Other property-related expenses (in USD $)
        :param gross_income: In USD ($).  Your share of gross income from the mine/well.
        """
        percent_depletion = self._percent[self._mineral]
        is_oil_or_gas = self._mineral in [self.MINERALS.OIL, self.MINERALS.GAS, self.MINERALS.OIL_SHALE]
        ceiling = .5 if not is_oil_or_gas else 1
        agi = gross_income if agi is None else agi
        oil_and_gas_cap = .65 * agi if is_oil_or_gas else 0

        taxable_income = gross_income - expenses
        depletion_allowance = min(percent_depletion * gross_income, ceiling * taxable_income)

        taxable_income -= depletion_allowance
        if is_oil_or_gas and taxable_income > oil_and_gas_cap:
            depletion_allowance -= (taxable_income - oil_and_gas_cap)

        return depletion_allowance

    def depreciate(self, date, **kwargs):
        relative_year = (date - self._date_put_into_service) // 365 + 1
        if relative_year in self._accumulated_depletion:
            return self._accumulated_depletion[relative_year]

        depletions = [0]
        for method in [self._cost_depletion, self._percent_depletion]:
            try:
                depletions += [method(**kwargs)]
            except (KeyError, TypeError) as terr:
                pass

        # The depletion method we use must be the one that gives the largest deduction
        depletion = max(depletions)
        self._accumulated_depletion[relative_year] = depletion
        self._cost_recovery += depletion
        return depletion

    def accumulated_depreciation(self, date):
        return self._add_cumulative(date, 1)

    def accumulated_depreciation_to_date(self, date):
        return self._add_cumulative(date)

    def _add_cumulative(self, date, extra=0):
        relative_year = (date - self._date_put_into_service) // 365 + 1
        total = 0
        for year in range(relative_year + extra):
            total += self._accumulated_depletion[year]
        return total

    def get_depletion(self, year):
        return self._accumulated_depletion[year]


class BusinessUseBasis(BusiInvBasis):
    pass


class InvestmentUseBasis(BusiInvBasis):

    def return_of_capital(self, adjustment):
        """Adjusts basis for a recognition of ROC"""
        self._other_reductions += adjustment


class PersonalUseBasis(AdjustedBasis):

    def convert(self, fmv):
        """Converts a property's basis from personal-use to business-use"""
        return min(self.adjusted_basis(), fmv)

    def depreciate(self, amount):
        # So while I'd love to raise an error here (raise TypeError("Cannot depreciate personal use property")),
        # this winds up getting us into trouble with ducktyping.  Therefore, I'll just do nothing here.
        return 0


# TODO: GiftBasis


class RelatedPartyBasis(BusinessUseBasis):
    """For when a related party transaction takes place"""

    def __init__(self, cost, gain_or_loss_by_other_party, liability_assumed=0, notes_to_seller=0, unstated_interest=0,
                 date_put_into_service=None, life=5, macrs_table=None):
        self.suspended_gainloss = gain_or_loss_by_other_party
        super().__init__(cost=cost, liability_assumed=liability_assumed, notes_to_seller=notes_to_seller,
                         unstated_interest=unstated_interest, life=life, macrs_table=macrs_table,
                         date_put_into_service=date_put_into_service)


class ImprovementBasis(BusinessUseBasis):
    """For improvements made to the property after it's gone into use or for leasehold improvements"""

    def __init__(self, cost, description="", **kwargs):
        super().__init__(cost, **kwargs)
        self.description = description

    def is_elevator(self):
        return 'elevator' in self.description

    def is_escalator(self):
        return 'escalator' in self.description

    def is_enlarging(self):
        enlarge_words = ['enlarge', 'expand', 'addition']
        for word in enlarge_words:
            if word in self.description:
                return True
        return False

    def is_modifying_internal_framework(self):
        return 'internal framework' in self.description

    def is_qip(self):
        funcs = [self.is_enlarging, self.is_escalator, self.is_elevator, self.is_modifying_internal_framework]
        for func in funcs:
            if func():
                return False
        return True


class AggregateAB(Aggregated):

    def _aggregate(self, attr_name):
        # For dual basis items, I'll allow you to pass through a tuple of (attr_name, selling price)
        sales_price = None
        if isinstance(attr_name, (tuple, list)):
            attr_name, sales_price = attr_name

        total = 0
        for item in self:
            try:
                actual_attr = getattr(item, attr_name)
                if callable(actual_attr):
                    total += actual_attr(sales_price=sales_price)
                else:
                    total += actual_attr
            except AttributeError:
                continue

        return total

    def __getitem__(self, item):
        if not isinstance(item, (tuple, list)):
            return super().__getitem__(item)
        return self._aggregate(item)

    def __getattr__(self, item):
        return self._aggregate(item)

    def transfer_adjustment(self, new_ab, date=None, tax_year_start=None):
        """
        This is if you are transferring the AB from one entity to another entity.
        Ex. through contribution or distribution.
        AB is no longer uniform -- any gain/loss in the AB due to the transfer is depreciated separately

        Returns the depreciation expense for that transition year if you supply the dates
        """
        main_ab = self[0]
        # Create a new AB object for the difference between the new AB and the AB now (before adjustment)
        ab_obj = type(main_ab)(new_ab - self.ab, date_put_into_service=date, life=main_ab.life,
                               macrs_table=main_ab.macrs_table)
        # Now we must figure out how much depreciation expense is for each entity for the partial year
        original_entity, new_entity = None, None
        if date is not None:
            beginning_year = date.month - tax_year_start.month
            end_year = 12 - beginning_year
            nmonths = {'original_entity': beginning_year, 'new_entity': end_year}

            tax_year_end = tax_year_start.add_one_year_less_one_day()
            # Find the amount of depreciation you would have taken if it were the same entity for the whole year
            depreciation_usually_taken = functools.reduce(lambda a, b: a + b.depreciate(tax_year_end), self, 0)
            # Multiply that by # months owned / 12
            original_entity = depreciation_usually_taken * (nmonths['original_entity'] / 12)
            new_entity = depreciation_usually_taken * (nmonths['new_entity'] / 12)
            # Finally, we need to add the additional depreciation from the new object we just created
            new_entity += ab_obj.depreciate(tax_year_end)

        self.append(ab_obj)
        return original_entity, new_entity


class Property(ABC):
    AB_SUBCLASS = AdjustedBasis
    CHARACTER = GLCharacter.CAP_GL

    def __init__(self, ab, fmv, liability=0, selling_expenses=0, date_acquired=None,
                 business_liability=0, personal_liability=0, date_sold=None, life=None, suspended_loss=0):
        """
        :param ab: adjusted basis
        :param fmv: fair market value
        :param liability: the liability
        :param selling_expenses: expenses to sell asset
        :param date_acquired: The date you acquired the property (or date put into service if applicable)
        :param business_liability: int/float.  This is really here for corporate contribution property.
            The nature of the liability on contributed property is very important and should be divided between the
            liability taken out for business reasons vs. personal reasons.
            IF YOU ARE NOT DEALING WITH A CORPORATION, please use the liability parameter instead.
        :param personal_liability: int/float.  Only relevant for corporate contribution property.
        :param date_sold: if/when the property is sold, this would be the date it was sold
        :param life: int.  If the property has a useful life for depreciation, supply it here please.
        :param suspended_loss: This only applies if the property is acquired in a related party transaction,
            and the person who sold the property to you did so at a loss.  This should be the amount of the
            suspended loss that the person who sold it to you could not take.
            MAKE SURE IT IS NEGATIVE (since it is a loss!)
        """
        life = life if life is not None else self.default_life
        ab_class = self.AB_SUBCLASS(ab, life=life, date_put_into_service=date_acquired)
        if date_acquired:
            ab_class._date_put_into_service = date_acquired

        self._ab_with_class = AggregateAB([ab_class])
        self._fmv = fmv
        self._introduce_liability(liability=liability, business_purpose=business_liability,
                                  personal_liab=personal_liability, date_acquired=date_acquired)
        # TODO: Add back in with Gift Basis
        # self._contains_dual_basis_items = True if isinstance(ab_class, GiftBasis) else False
        self._contains_dual_basis_items = False

        # Some additional things about the asset
        self.selling_expenses = selling_expenses
        self.date_acquired = date_acquired
        self.date_sold = date_sold

        # For suspended losses (if you acquired the asset from a related party and they sold it to you at a loss)
        if suspended_loss > 0:
            raise ValueError("Suspended loss must be a loss (i.e. less than 0)")
        self.suspended_loss = suspended_loss

        # For if you need to set this (ex. for gift basis items)
        self.sales_price = None

        # We will calculate this later
        self.new_ab = None

        # Expense bills/invoices identified by invoice/billing number
        self._expenses = {}
        self._last_number = 1000001
        self._income_from_property = {}

    def _introduce_liability(self, liability, business_purpose, personal_liab, date_acquired=None):
        if not business_purpose and not personal_liab:
            if not isinstance(liability, Liability):
                liability = Liability(liability, date_incurred=date_acquired)
            self._liability = liability
        else:
            self._liability = Aggregated([liability, business_purpose, personal_liab])

    def holding_period(self, end_date):
        return days_between(end_date, self.date_acquired) // 365

    @property
    def ab(self):
        if self._contains_dual_basis_items:
            return self._ab_with_class[('adjusted_basis', self.sales_price)]
        return self._ab_with_class.ab

    @ab.setter
    def ab(self, value):
        if isinstance(value, list):
            value = Aggregated([AdjustedBasis(x) if not isinstance(x, AdjustedBasis) else x for x in value])
        elif not isinstance(value, AdjustedBasis):
            value = AdjustedBasis(value)

        self._ab_with_class = value

    @property
    def fmv(self):
        return self._fmv

    @fmv.setter
    def fmv(self, value):
        self._fmv = value

    @property
    @abstractmethod
    def does_holding_period_tack(self):
        pass

    @property
    @abstractmethod
    def category(self):
        pass

    @property
    def default_life(self):
        return 5

    @property
    def liability(self):
        return self._liability

    def basis(self, **kwargs):
        return self._ab_with_class.basis_for_depr

    @property
    def ab_obj(self):
        return self._ab_with_class

    @property
    def cost_recovery(self):
        return self.ab_obj.cost_recovery

    @abstractmethod
    def recapture(self, gainloss, **kwargs):
        """Takes gain/loss as parameter.  Returns the portion of g/l that is ordinary income"""
        pass

    @abstractmethod
    def recapture_as_lambda(self):
        pass

    def percent_used_for_gain_seeking_purposes(self, **kwargs):
        """Returns a float between 0 and 1"""
        return 1

    def depreciate(self, year):
        return sum([x.depreciate(year) for x in self._ab_with_class])

    def basis_for_depreciation(self, year):
        return sum([x.basis_for_depreciation(year=year) for x in self._ab_with_class])

    @classmethod
    def c_corp(cls, *args, personal_liability=0, business_liability=0, **kwargs):
        return CCorpProp(cls(*args, **kwargs), personal_liability=personal_liability,
                         business_liability=business_liability)

    # To record expenses and income made from the property

    def record_expense(self, id_number, date_billed, amount_billed_for, description, category,
                       date_paid=None, amount_paid=None, nondeductible_portions=0):
        """Records an expense you were billed or invoiced for with regards to this property"""
        if 'property tax' in category:
            category = 'real estate tax'
        self._expenses[id_number] = InvoiceOrBill(id_number, date_billed, amount_billed_for, description=description,
                                                  category=category, nondeductible_portions=nondeductible_portions)
        if date_paid and amount_paid:
            self.record_expense_payment(id_number, date_paid, amount_paid)

    def record_expense_payment(self, id_number, date_paid, amount_paid):
        """Records a payment on a billed/invoiced expense item"""
        self._expenses[id_number].pay(date_paid, amount_paid)

    @property
    def mortgage_interest_category_name(self):
        return 'interest expense on property'

    def pay_off_liability(self, date, principal_portion, interest_portion, liability_number=1, is_form_1098=False):
        """To repay a liability on this property"""
        description = 'interest expense on property'
        if is_form_1098:
            description += " from form 1098"

        liab = self._liability
        if isinstance(self._liability, list):
            liab = self._liability[liability_number - 1]
        liab.repay_principal(principal_portion, interest_amount=interest_portion, date=date)
        self._expenses[f'A{self._last_number}'] = InvoiceOrBill(f"A{self._last_number}", date, interest_portion,
                                                                description=description,
                                                                category=self.mortgage_interest_category_name)
        self.record_expense_payment(f"A{self._last_number}", date, interest_portion)
        self._last_number += 1

    def get_interest_expense(self, end_tax_year):
        amounts = []
        for interest_expense_category in {'interest expense on property', self.mortgage_interest_category_name,
                                          'interest expense on property from form 1098'}:
            amounts += self._get_expense(end_tax_year, interest_expense_category,
                                         lambda invc, start_ty, end_ty: invc.amount_billed_this_year(start_ty, end_ty))
        return sum([y for x, y in amounts])

    def list_interest_expense(self, end_tax_year):
        amounts = []
        for interest_expense_category in {'interest expense on property', self.mortgage_interest_category_name,
                                          'interest expense on property from form 1098'}:
            amounts += self._get_expense(end_tax_year, interest_expense_category,
                                         lambda invc, start_ty, end_ty: invc.amount_billed_this_year(start_ty, end_ty))
        return amounts

    def _get_expense(self, end_tax_year, category, func):
        start_tax_year = back_one_year(end_tax_year, less_one_day=True)

        this_year = []
        for invoice in self._expenses.values():
            if category is not None and invoice.category != category:
                continue
            amount_that_counts = func(invoice, start_tax_year, end_tax_year)

            if amount_that_counts:
                this_year.append((invoice, amount_that_counts))
        return this_year

    def get_expenses_paid_this_year(self, end_tax_year, category):
        """Retrieves any expenses on the current property paid during the current year that are in category"""
        return self._get_expense(end_tax_year, category,
                                 lambda invc, start_ty, end_ty: invc.amount_paid_this_year(start_ty, end_ty))

    def get_expenses_billed_this_year(self, end_tax_year, category):
        return self._get_expense(end_tax_year, category,
                                 lambda invc, start_ty, end_ty: invc.amount_billed_this_year(start_ty, end_ty))

    def record_income(self, date, amount, **kwargs):
        self._income_from_property.setdefault(date, Aggregated())
        kwargs.update({'date': date, 'amount': amount})
        self._income_from_property[date].append(kwargs)

    def get_income_items(self):
        return self._income_from_property

    @property
    def is_for_rental(self):
        try:
            return self._is_for_rental
        except AttributeError:
            return False

    @is_for_rental.setter
    def is_for_rental(self, value):
        self._is_for_rental = value

    # More stuff dealing with basis

    def is_short_term(self, current_date):
        if self.date_acquired is None:
            return self.holding_period < 1
        first_date_of_ownership = timestamp_to_date(make_timestamp(self.date_acquired) + 24 * 60 * 60)
        date_req_to_be_ltcg = datetime.date(month=first_date_of_ownership.month,
                                            day=first_date_of_ownership.day,
                                            year=first_date_of_ownership.year + 1)

        return current_date < date_req_to_be_ltcg

    def add_new_basis_chunklet(self, basis_obj):
        """
        This is for if you need to create a new basis chunklet for improvements to the property at a later date
        or for section 741 (partnership) adjustments or for whatever else you need to do.
        The original basis will remain the same and be depreciated the same, but this new basis will be tacked onto it.
        """
        self._ab_with_class.append(basis_obj)


class CCorpProp(Property):

    def __init__(self, personal_liability=0, business_liability=0, **kwargs):
        """
        :param personal_liability: liability taken out FOR NON_BUSINESS PURPOSES or tax avoidance purposes
            (Note: if for BUSINESS PURPOSES, then section 357(a) applies and it's NOT considered a boot.)
            (Also note: a mortgage (attached to property) is considered a business purpose.)
        :param business_liability: liability taken out for business purposes
        """
        super().__init__(**kwargs)
        self._introduce_liability(business_liability=business_liability, personal_liability=personal_liability)

        # We will calculate this later
        self.corp_ab = None

    def _introduce_liability(self, business_liability, personal_liability, **kwargs):
        # A partially personal liability and a partially business liability taints the liability so it's all personal
        if personal_liability and business_liability:
            personal_liability += business_liability
            business_liability = 0

        self.business_liability = Liability(business_liability)
        self.personal_liability = Liability(personal_liability)

    @property
    def liability(self):
        return self.personal_liability.fmv + self.business_liability.fmv

    @property
    def ab_obj(self):
        return self._ab_with_class

    @property
    def cost_recovery(self):
        return self.ab_obj.cost_recovery

    @abstractmethod
    def recapture(self, gainloss, **kwargs):
        pass

    @abstractmethod
    def recapture_as_lambda(self):
        pass


class FloorPlanFinancing(object):

    def __init__(self, amount, interest, interest_deduction_taken):
        self.amount = amount
        self.interest = interest
        self.interest_deduction_taken = interest_deduction_taken


class RecapturedProperty(Property):

    def __init__(self, ab, fmv, liability=0, selling_expenses=0, date_acquired=None,
                 business_liability=0, personal_liability=0, business_floor_plan_financing=None,
                 is_used_leased_or_financed_by_tax_exempt_org=False, is_used_predominantly_outside_us=False,
                 is_imported_from_country_with_discriminator_trade_practices=False, is_regulated_public_utility=False,
                 **kwargs):
        super().__init__(ab=ab, fmv=fmv, liability=liability, selling_expenses=selling_expenses,
                         business_liability=business_liability,
                         personal_liability=personal_liability,
                         date_acquired=date_acquired, **kwargs)
        self.business_floor_plan_financing = business_floor_plan_financing
        self.is_used_predominantly_outside_us = is_used_predominantly_outside_us
        self.is_imported_from_country_with_discriminator_trade_practices = is_imported_from_country_with_discriminator_trade_practices
        self.is_used_leased_or_financed_by_tax_exempt_org = is_used_leased_or_financed_by_tax_exempt_org
        self.is_regulated_public_utility = is_regulated_public_utility

    def recapture(self, gainloss, cost_recovery=None, to_related_party=False):
        cost_recovery = cost_recovery if cost_recovery is not None else self.cost_recovery
        if gainloss < 0:
            return 0
        # All ordinary income if sold to a related party
        if to_related_party:
            return gainloss
        return min(cost_recovery, gainloss)

    def recapture_as_lambda(self):
        cost_recovery = self.cost_recovery

        def recapture(gl):
            if gl < 0:
                return 0
            return min(cost_recovery, gl)

        return recapture


class UnRecapturedProperty(Property):

    def recapture(self, gainloss, cost_recovery=None, **kwargs):
        return 0

    def recapture_as_lambda(self):
        return lambda x: 0


class BusinessProperty(RecapturedProperty):
    """Property that is being used for business purposes and falls under Section1231"""
    AB_SUBCLASS = BusinessUseBasis

    @property
    def does_holding_period_tack(self):
        return True

    @property
    def category(self):
        return UseType.BUSINESS


class InvestmentProperty(RecapturedProperty):
    """Capital assets, like land"""
    AB_SUBCLASS = InvestmentUseBasis

    @property
    def does_holding_period_tack(self):
        return True

    @property
    def category(self):
        return UseType.INVESTMENT

    def get_income(self, **kwargs):
        """If this item produces income, it retrieves that income"""
        return 0

    @property
    def is_passive(self):
        try:
            return self._is_passive
        except AttributeError:
            return False

    @is_passive.setter
    def is_passive(self, value):
        self._is_passive = bool(value)


class BusinessQIP(BusinessProperty):
    """For qualified improvement property"""
    pass


class InvestmentQIP(InvestmentProperty):
    """For investment qualified property"""
    pass


class BusinessLand(BusinessProperty):
    CHARACTER = GLCharacter.CAP_GL

    @property
    def cost_recovery(self):
        return 0

    def recapture(self, gainloss, **kwargs):
        return 0

    def recapture_as_lambda(self):
        return lambda x: 0

    @property
    def default_life(self):
        return float('inf')

    @property
    def address(self):
        return self._address

    @address.setter
    def address(self, value):
        self._address = value


class InvestmentLand(BusinessProperty):
    CHARACTER = GLCharacter.CAP_GL

    @property
    def cost_recovery(self):
        return 0

    def recapture(self, gainloss, **kwargs):
        return 0

    def recapture_as_lambda(self):
        return lambda x: 0

    @property
    def default_life(self):
        return float('inf')

    @property
    def address(self):
        return self._address

    @address.setter
    def address(self, value):
        self._address = value


class ListedProperty(ABC):
    """
    Property falls into two categories and must be allocated.
    This is a parent class.
    """
    CHARACTER = GLCharacter.SPLIT
    BusPers = collections.namedtuple("BusPers", ["business", "personal"])
    BusVest = collections.namedtuple("BusVest", ['business', 'investment'])
    VestPers = collections.namedtuple("VestPers", ['investment', 'personal'])

    @classmethod
    def _tuple_type(cls):
        raise NotImplementedError("Please Implement this")

    def __init__(self, ab, fmv, liability=0, selling_expenses=0, holding_period=0, date_acquired=None,
                 life=None, **kwargs):
        self._ab = ab

        life = life or self.default_life
        ab_with_class = ab if isinstance(ab, AdjustedBasis) else BusinessUseBasis(ab, life=life)
        if date_acquired is not None:
            ab_with_class._date_put_into_service = date_acquired

        self._ab_with_class = Aggregated([ab_with_class])
        self._fmv = fmv
        self._liability = liability
        self._selling_expenses = selling_expenses
        self._holding_period = holding_period
        self._depreciation_by_year = {}

        self._personal_subclass = PersonalUseProperty
        self._business_subclass = BusinessProperty

    @property
    def _basis(self):
        return self._ab_with_class.basis_for_depr

    @abstractmethod
    def percent_qual_use(self, **kwargs):
        pass

    @abstractmethod
    def basis(self, **kwargs):
        pass

    def basis_for_depreciation(self, year):
        return sum([x.basis_for_depreciation(year=year) for x in self._ab_with_class])

    @property
    def default_life(self):
        return 5

    @staticmethod
    def _get_percents(percent_business_use):
        percent_business = percent_business_use if percent_business_use <= 1 else percent_business_use / 100
        percent_personal = 1 - percent_business_use
        return percent_business, percent_personal

    @classmethod
    def _allocate(cls, percent_business, percent_personal, total_amount):
        return cls._tuple_type()(total_amount * percent_business, total_amount * percent_personal)

    def _allocate_objs(self, percent_business, percent_personal):
        """Allocates between two objects, a business object and a personal object"""
        attr_names = ['ab', 'fmv', 'liability', 'selling_expenses']
        attrs = [self._ab, self._fmv, self._liability, self._selling_expenses]
        alloc_attrs = [self._allocate(percent_business, percent_personal, original_val) for original_val in attrs]

        attr_names.append("holding_period")
        alloc_attrs.append(self._holding_period)

        pers = {k: v.personal for k, v in zip(attr_names, alloc_attrs)}
        bus = {k: v.business for k, v in zip(attr_names, alloc_attrs)}

        bus_obj, pers_obj = self._business_subclass(**bus), self._personal_subclass(**pers)

        return bus_obj, pers_obj

    @classmethod
    def from_other_property(cls, other_property, year, percent):
        """Converts other property into listed property"""
        new = cls(ab=other_property.ab, fmv=other_property.fmv, liability=other_property.liability,
                  selling_expenses=other_property.selling_expenses, holding_period=other_property.holding_period,
                  percent_business_use={year: percent})
        if isinstance(other_property, BusinessProperty):
            new._business_subclass = type(other_property)
        elif isinstance(other_property, PersonalUseProperty):
            new._personal_subclass = type(other_property)

    @property
    def ab_obj(self):
        return self._ab_with_class

    def percent_used_for_gain_seeking_purposes(self, **kwargs):
        return self.percent_qual_use(**kwargs)

    def depreciate(self, year):
        return sum([x.depreciate(year) for x in self._ab_with_class])


class BusiPersProperty(ListedProperty):
    """Partially used for business and partially used for personal use"""

    def __init__(self, ab, fmv, percent_business_use, liability=0, selling_expenses=0,
                 business_subclass=None, personal_subclass=None, **kwargs):
        super().__init__(ab, fmv, liability, selling_expenses, **kwargs)
        self._business_subclass = business_subclass if business_subclass is not None else BusinessProperty
        self._personal_subclass = personal_subclass if personal_subclass is not None else PersonalUseProperty

        if isinstance(percent_business_use, dict):
            percent_business_use = percent_business_use.popitem()[1]
        self._percent_business, self._percent_personal = self._get_percents(percent_business_use)
        self._business_object, self._personal_object = self._allocate_objs(self._percent_business,
                                                                           self._percent_personal)

    @abstractmethod
    def percent_qual_use(self, **kwargs):
        return self._percent_business

    @property
    def business(self):
        return self._business_object

    @property
    def personal_use(self):
        return self._personal_object

    @classmethod
    def _tuple_type(cls):
        return cls.BusPers

    def basis(self, **kwargs):
        allocated = self._allocate(self._percent_business, self._percent_personal, self._basis)
        return allocated.business

    def percent_used_for_gain_seeking_purposes(self, **kwargs):
        """Returns a float between 0 and 1"""
        return self.percent_qual_use(**kwargs)


class BusiPersPropertyChanging(ListedProperty):
    """partially personal, partially business, and percent changes based on the year"""

    def __init__(self, ab, fmv, percent_business_use: dict = None, liability=0, selling_expenses=0, holding_period=0,
                 business_subclass=None, personal_subclass=None, **kwargs):
        super().__init__(ab, fmv, liability, selling_expenses, holding_period, **kwargs)
        self._business_subclass = business_subclass if business_subclass is not None else BusinessProperty
        self._personal_subclass = personal_subclass if personal_subclass is not None else PersonalUseProperty

        self._usage_percentages = {}
        if percent_business_use is not None:
            for year, percent_bus in percent_business_use.items():
                self.add_year(year, percent_bus)

    def percent_qual_use(self, year, **kwargs):
        return self._usage_percentages[year].business

    def basis(self, year, **kwargs):
        usage = self._usage_percentages[year]
        # Okay, I'm going to go with the idea that these are all little chunklets of AB, and that each year,
        # you calculate depreciation on a different little chunklet.  I have no idea if that is right.
        adjustments = self._ab_with_class.section179_and_bonus_depr
        basis = self._basis + adjustments
        allocated = self._allocate(usage.business, usage.personal, basis)
        return allocated.business - adjustments

    def entire_basis(self, **kwargs):
        """Entire unadjusted basis, unallocated"""
        return self._basis

    @classmethod
    def _tuple_type(cls):
        return cls.BusPers

    def add_year(self, year, business_use_percent):
        bus, pers = self._get_percents(business_use_percent)
        self._usage_percentages[year] = self._tuple_type()(bus, pers)

    def personal(self, year):
        percent = self._usage_percentages[year]
        bus, pers = self._allocate_objs(percent.business, percent.personal)
        return pers

    def business(self, year):
        percent = self._usage_percentages[year]
        bus, pers = self._allocate_objs(percent.business, percent.personal)
        return bus


class Automobile(BusiPersPropertyChanging):

    def __init__(self, ab, fmv, weight, percent_business_use: dict = None, liability=0, selling_expenses=0,
                 date_acquired=None, seating_capacity=5, length_of_open_bed_cargo_area=0,
                 has_an_integral_enclosure=False, has_no_seats_behind_drivers_seat=False,
                 has_no_body_section_over_30_inches_from_windshield=False,
                 business_floor_plan_financing=None, is_regulated_public_utility=False, **kwargs):
        """
        :param ab: Adjusted basis.  Can be AB object or a number (that I will convert to an AB object)
        :param fmv: The fair market value at the current date
        :param weight: The weight of the vehicle (in lbs)
        :param seating_capacity: The number of seats in the vehicle, EXCLUDING the driver's seat
        :param percent_business_use: A dictionary representing {year (int): percent business use (float)}  Business use
                also includes investment use.
        :param liability: Any liabilities encumbering the automobile that are attached to it
        :param selling_expenses: If being sold, this is accumulated selling expenses
        :param holding_period: The holding period of the object so far
        :param length_of_open_bed_cargo_area: Length (in feet) an open-bed cargo area that is designed to be an open
            area and not readily accessible from the passenger department.  If the vehicle does not have one, this
            should be zero (or will default to zero)
        :param has_an_integral_enclosure: boolean (default False).  Does your auto have an integral enclosure?
        :param has_no_seats_behind_drivers_seat: boolean (default False).  Does your auto have no seats behind driver?
        :param has_no_body_section_over_30_inches_from_windshield: boolean (default False). Does your auto have no
            body section over 30 inches from the windshield?
        """
        self.weight = weight
        self._seating_capacity = seating_capacity
        self._len_open_cargo_bed = length_of_open_bed_cargo_area
        self._is_truck = has_an_integral_enclosure or has_no_seats_behind_drivers_seat or has_no_body_section_over_30_inches_from_windshield

        self.business_floor_plan_financing = business_floor_plan_financing
        self.is_regulated_public_utility = is_regulated_public_utility

        super().__init__(ab=ab, fmv=fmv, percent_business_use=percent_business_use, liability=liability,
                         selling_expenses=selling_expenses, date_acquired=date_acquired, **kwargs)

    def is_truck(self):
        if self.weight < 6_000:
            return False
        if self._seating_capacity < 9:
            return False
        if self._len_open_cargo_bed < 6:
            return False
        return self._is_truck


class PassengerAuto(Automobile):
    pass


class TruckSUV(Automobile):
    pass


class Inventory(UnRecapturedProperty):
    AB_SUBCLASS = BusinessUseBasis
    CHARACTER = GLCharacter.ORDINARY

    @property
    def does_holding_period_tack(self):
        return False

    @property
    def category(self):
        return UseType.BUSINESS


class PersonalUseProperty(UnRecapturedProperty):
    """Any other type of property"""
    AB_SUBCLASS = PersonalUseBasis
    CHARACTER = GLCharacter.ORDINARY

    @property
    def does_holding_period_tack(self):
        return False

    @property
    def category(self):
        return UseType.PERSONAL


class PersonalUseRealty(PersonalUseProperty):
    """For real estate that is personal use"""

    def record_property_tax_invoice(self, id_number, date_billed, amount_billed, special_assessment_amount=0,
                                    date_paid=None, amount_paid=None):
        """
        :param id_number: Invoice # or Billing #.  Must be unique.
        :param date_billed: The date that appears on the invoice.
        :param amount_billed: The amount that appears on the invoice.
        :param special_assessment_amount: This parameter exists in case part of the amount_billed parameter is caused by
            a special assessment for a local improvement (which is not tax deductible and should be added to the basis).

            If amount billed does NOT include a special assessment for a local improvement (b/c it's billed separately
            or because there is no special assessment), this parameter should be 0.
            Please remember that special assessments should be added to the basis of the property!
            (Actually, they should really be added to the basis of the land)
        :param date_paid: If you have the date paid at this time, you can include that here as well.
        :param amount_paid: If you have the amount you paid, you may include it here.
        """

        self.record_expense(id_number, date_billed, amount_billed, description="property taxes",
                            category='real estate tax', date_paid=date_paid, amount_paid=amount_paid,
                            nondeductible_portions=special_assessment_amount)
        # TODO: Figure out a way to stick the special assessment value onto the land that goes with the property,
        #  rather than the structure of the property
        self.ab_obj.append(self.AB_SUBCLASS(special_assessment_amount))

    def record_property_tax_payment(self, id_number, date, amount):
        self.record_expense_payment(id_number, date, amount)

    # Qualified residence means that you can take a deduction for mortgage interest paid
    #  You can have 2 qualified residences

    @property
    def is_qualified_residence(self):
        if hasattr(self, 'is_principal_residence') and self.is_principal_residence:
            return True

        try:
            return self._is_qualified_residence
        except AttributeError:
            return False

    @is_qualified_residence.setter
    def is_qualified_residence(self, value):
        self._is_qualified_residence = value

    # Principal Residence means that you can exclude $250,000 ($500,000 if mfj) from cap gains if sold

    @property
    def is_principal_residence(self):
        try:
            return self._is_principal_residence
        except AttributeError:
            return False

    @is_principal_residence.setter
    def is_principal_residence(self, value):
        self._is_principal_residence = bool(value)

    @property
    def address(self):
        return self._address

    @address.setter
    def address(self, value):
        self._address = value

    def add_liability(self, date_incurred, amount, is_used_to_buy_build_or_improve_property):
        """This is for when you take out a liability on the property that is """
        reason = 'building_improvements' if is_used_to_buy_build_or_improve_property else 'personal'
        if not isinstance(self._liability, list):
            self._liability = Aggregated([self._liability])

        self._liability.append(Liability(amount, date_incurred=date_incurred, reason=reason))

    def home_equity_indebtedness(self):
        total = 0
        acquisition_indebtedness = 0

        # This happens when only acquisition indebtedness
        if not isinstance(self._liability, list):
            return LimitedAmount(upper_limit=0), []

        indebtedness = []
        for liability in self._liability:
            if liability.reason == 'building_improvements':
                total += liability.fmv
                indebtedness.append(liability)
            elif liability.reason == 'acquisition':
                acquisition_indebtedness += liability.fmv
            # The limitation on home equity indebtedness needing to be building improvements is only around for
            # debt incurred between 2018 to 2025, inclusive.
            elif liability.date_incurred is not None:
                if liability.date_incurred.year < 2018 or liability.date_incurred > 2025:
                    total += liability.fmv
                    indebtedness.append(liability)

        # Maximum home equity indebtedness is the FMV of the property - the acquisition indebtedness
        return LimitedAmount(upper_limit=self.fmv - acquisition_indebtedness, start=total), indebtedness

    def acquisition_indebtedness(self):
        # This happens when only acquisition indebtedness
        if not isinstance(self._liability, list):
            return [self._liability]
        return Aggregated([x for x in self._liability if x.reason == 'acquisition'])

    def _standard_1001_sale(self, date, amount_received, selling_expenses):
        gainloss = amount_received + self.liability - self.ab - selling_expenses
        # Can't recognize a loss on a personal use asset
        if gainloss < 0:
            return AllGainSale()
        if self.is_short_term(date):
            return AllGainSale(st_capgain=gainloss)
        return AllGainSale(lt_capgain=gainloss)

    @staticmethod
    def _qualified_vs_nonqualified_proration(current_date, total_years, num_years_living_there, exclusion_amount):
        """
        Prorates between the number of years living there and the number of years not living there.
        Note that for members of the active duty military, the total number of years is 15 (not 5).
        """
        start_of_years = current_date.year - total_years
        years_before_2009 = 0 if start_of_years >= 2009 else 2009 - start_of_years

        qualified = num_years_living_there + years_before_2009

        return qualified / total_years * exclusion_amount

    def sell(self, date, amount_received, is_mfj=False, num_years_living_there_out_of_past_5=None,
             is_moving_for_qual_reason=False, is_military=False, selling_expenses=0, empty_list=None, **kwargs):
        """
        To sell the property
        If you are NOT selling your primary residence, you only need to supply:
            the date
            the amount received
            any selling expenses

        :param date: The date of the sale
        :param amount_received: the cash/fmv of property received.  Do not include mortgages attached to the property,
            as I add these in myself.
        :param is_mfj: Bool.
        :param num_years_living_there_out_of_past_5: Of the past 5 years, how many years have you lived in the
            property as your primary residence?
            Note that if you have lived there for under 2 years, you must write this as a float of the number of
                months you occupied the property.
        :param is_moving_for_qual_reason: Bool.  If you are moving early (i.e. before 2 years is up), was it for
            a qualified reason?  Ex. if you had to move because your job required you.
        :param is_military: Bool.  If you are a member of the active duty military, you get 15 years, not 5.  Please
            answer True to this parameter and write the number of years living in the residence out of the past 15 years
            instead of 5 for the previous parameter.
        :param empty_list: optional.  if you pass through an empty list here, I will populate it with the exclusion
            amount (if applicable)
        :return: gain recognized
        """
        # If it's NOT primary residence, then this is your normal section 1001 sale
        if not self.is_principal_residence:
            return self._standard_1001_sale(date, amount_received, selling_expenses)

        if num_years_living_there_out_of_past_5 < 2 and not is_moving_for_qual_reason:
            return self._standard_1001_sale(date, amount_received, selling_expenses)

        exclusion_amount = 500_000 if is_mfj else 250_000
        total_years = 5 if not is_military else 15

        if num_years_living_there_out_of_past_5 < 2:
            months = num_years_living_there_out_of_past_5 * 12
            proration = exclusion_amount * months / 24
            total_exclusion = proration * exclusion_amount
        else:
            total_exclusion = self._qualified_vs_nonqualified_proration(
                date, total_years, num_years_living_there_out_of_past_5, exclusion_amount)

        if empty_list is not None:
            empty_list.append(total_exclusion)

        # I'll just add the total exclusion into something that will be used to reduce the gainloss
        return self._standard_1001_sale(date, amount_received, selling_expenses + total_exclusion)


class JointlyOwnedHome(PersonalUseRealty):
    """
    A jointly owned home between two individuals (who may be divorced or not).
    Note that although this does not have to be Qualified Residence, it might be.
    """

    class OwnershipType(enum.Enum):
        TENANTS_IN_COMMON = enum.auto()
        JOINT_TENANCY = enum.auto()
        TENANTS_BY_ENTIRETY = enum.auto()

    class ExpensePayments(enum.Enum):
        MORTGAGE_PRINCIPAL = enum.auto()
        MORTGAGE_INTEREST = enum.auto()
        REAL_ESTATE_TAXES = enum.auto()
        HOME_INSURANCE = enum.auto()
        OTHER = enum.auto()

    def __init__(self, owner1, owner2, ownership_type, ab, fmv, mortgage, **kwargs):
        self._owners = [owner1, owner2]
        self.ownership = self._convert_to_enum(ownership_type, self.OwnershipType)
        super().__init__(ab, fmv, mortgage, **kwargs)

        self._allocated_expense_payments = {}

    @staticmethod
    def _convert_to_enum(name, enum_class):
        if isinstance(name, str):
            return enum_class[name.upper().replace(" ", "_")]
        return name

    def allocate_expense(self, expense_type, amount_per_month, owner_allocated_to):
        """Allocates a monthly expense payment to a particular owner.  If not monthly, make monthly"""
        expense_type = self._convert_to_enum(expense_type, self.ExpensePayments)
        self._allocated_expense_payments.setdefault(expense_type, {})
        self._allocated_expense_payments[expense_type][owner_allocated_to] = amount_per_month

    def get_expense(self, expense_type, owner_allocated_to=None):
        expense_type = self._convert_to_enum(expense_type, self.ExpensePayments)
        first_dict = self._allocated_expense_payments[expense_type]
        if owner_allocated_to is None:
            return first_dict
        return first_dict[owner_allocated_to]


class PersonalDebt(UnRecapturedProperty):
    AB_SUBCLASS = PersonalUseBasis

    def __init__(self, amount_of_debt):
        super().__init__(0, 0, amount_of_debt)

    @property
    def does_holding_period_tack(self):
        return False

    @property
    def category(self):
        return UseType.PERSONAL

    def __neg__(self):
        return type(self)(-self.liability)


class TaxExempt(InvestmentProperty):
    pass


class PublicSecurity(InvestmentProperty):
    CHARACTER = GLCharacter.CAP_GL

    def __init__(self, ab, fmv, liability=0, dividends_per_year=0, selling_expenses=0, holding_period=0,
                 date_acquired=None, **kwargs):
        self._dividends_per_year = dividends_per_year
        super().__init__(ab=ab, fmv=fmv, liability=liability, selling_expenses=selling_expenses,
                         holding_period=holding_period, date_acquired=date_acquired, **kwargs)

    def get_income(self):
        return self._dividends_per_year


class InvestmentStock(InvestmentProperty):
    """This is for stock that you buy for investment purposes.  So do not use it if you are accounting for a
    corporation that is issuing its own stock!"""
    CHARACTER = GLCharacter.CAP_GL

    def __new__(cls, cost_per_share, fmv_per_share, num_shares, date_acquired, liability=0,
                unrecognized_loss_from_related_party=0, **kwargs):
        if num_shares != int(num_shares):
            return InvestmentStockWithFractionalShares(
                cost_per_share=cost_per_share, fmv_per_share=fmv_per_share, num_shares=num_shares,
                date_acquired=date_acquired, liability=liability,
                unrecognized_loss_from_related_party=unrecognized_loss_from_related_party, **kwargs)
        return super(InvestmentStock, cls).__new__(cls)

    def __init__(self, cost_per_share, fmv_per_share, num_shares, date_acquired, liability=0,
                 unrecognized_loss_from_related_party=0, **kwargs):
        """
        :param cost_per_share: you bought the stock at this amount per share.
        :param fmv_per_share: if different, this is the fmv per share on the current date.
            This parameter is really just here if you're shortcutting so you initialize class when the stock is sold.
        :param num_shares: number of shares
        :param date_acquired: Date.  The date the stock was acquired.
        :param liability: int/float.  If there was a liability used to acquire the stock, record it here.
        :param unrecognized_loss_from_related_party: This is ONLY used if you acquired the stock from a related
            party, and they sold it to you at a loss.
            The suspended loss can sometimes offset your gain when you sell the stock.
            MAKE SURE THIS NUMBER IS NEGATIVE!  Otherwise, an exception will be raised because you cannot submit
                a gain here.
        """
        super().__init__(ab=0, fmv=fmv_per_share * num_shares, liability=liability,
                         date_acquired=date_acquired, suspended_loss=unrecognized_loss_from_related_party,
                         **kwargs)

        self._ab_with_class = Aggregated([self.AB_SUBCLASS(cost_per_share) for _ in range(int(num_shares))])

        self._num_shares = num_shares
        self._fmv_per_share = fmv_per_share

    @property
    def fmv_per_share(self):
        return self._fmv_per_share

    @fmv_per_share.setter
    def fmv_per_share(self, value):
        self._fmv_per_share = value

    @property
    def fmv(self):
        return self._fmv_per_share * self._num_shares

    @property
    def num_shares(self):
        return self._num_shares

    def get_holding_period(self, date):
        first_date_owned = self.date_acquired + 1

        years_since_first = date.year - first_date_owned.year
        rounded_up = datetime.date(month=first_date_owned.month, day=first_date_owned.day,
                                   year=first_date_owned.year + years_since_first)

        if rounded_up < date:
            return years_since_first - 1
        return years_since_first

    def ab_of(self, num_shares):
        return Aggregated(self._ab_with_class[:num_shares]).adjusted_basis

    def sell(self, date, num_shares, fmv_per_share_on_date_sold, **kwargs):
        fmv = num_shares * fmv_per_share_on_date_sold

        ab = Aggregated(self._ab_with_class[:int(num_shares)])
        self._ab_with_class = Aggregated(self._ab_with_class[int(num_shares):])
        self._num_shares -= num_shares

        gainloss = fmv - ab.ab

        # Related party offset: if this is a sale to an unrelated party of an asset from a related party,
        # you can offset gain by the amount of suspended loss from that other party
        if gainloss > 0:
            gainloss += max(0, -self.suspended_loss)

        # To classify it as LT or ST -- ownership takes place the day after you purchase the stock.
        if self.is_short_term(date):
            return AllGainSale(st_capgain=gainloss)
        return AllGainSale(lt_capgain=gainloss)

    def return_of_capital(self, amount):
        """Allows taxpayer to recognize a return of capital that decreases basis"""
        decrease_per_share = amount / self.num_shares
        [x.return_of_capital(decrease_per_share) for x in self._ab_with_class]

    def recapture(self, gainloss, cost_recovery=None, to_related_party=False):
        return 0

    def recapture_as_lambda(self):
        return lambda gl: 0

    def depreciate(self, year):
        return 0


class InvestmentStockWithFractionalShares(InvestmentStock):
    """This is for fractional shares because it was driving me crazy in the old class"""
    CHARACTER = GLCharacter.CAP_GL

    def __new__(cls, *args, **kwargs):
        return super(InvestmentStock, cls).__new__(cls)

    def __init__(self, cost_per_share, fmv_per_share, num_shares, date_acquired, liability=0,
                 unrecognized_loss_from_related_party=0, **kwargs):
        """
        :param cost_per_share: you bought the stock at this amount per share.
        :param fmv_per_share: if different, this is the fmv per share on the current date.
            This parameter is really just here if you're shortcutting so you initialize class when the stock is sold.
        :param num_shares: number of shares
        :param date_acquired: Date.  The date the stock was acquired.
        :param liability: int/float.  If there was a liability used to acquire the stock, record it here.
        :param unrecognized_loss_from_related_party: This is ONLY used if you acquired the stock from a related
            party, and they sold it to you at a loss.
            The suspended loss can sometimes offset your gain when you sell the stock.
            MAKE SURE THIS NUMBER IS NEGATIVE!  Otherwise, an exception will be raised because you cannot submit
                a gain here.
        """
        super(InvestmentStock, self).__init__(ab=cost_per_share * num_shares, fmv=fmv_per_share * num_shares,
                                              liability=liability,
                                              date_acquired=date_acquired,
                                              suspended_loss=unrecognized_loss_from_related_party,
                                              **kwargs)

        self._cost_per_share = cost_per_share
        self._num_shares = num_shares
        self.fmv_per_share = fmv_per_share

    @property
    def basis_per_share(self):
        return self._cost_per_share

    def adjust_basis_per_share(self, total_adjustment_amount):
        adjustment_per_share = total_adjustment_amount / self.num_shares
        self.ab_obj.append(self.AB_SUBCLASS(total_adjustment_amount))
        self._cost_per_share += adjustment_per_share

    def ab_of(self, num_shares):
        return self._cost_per_share * num_shares

    def sell(self, date, num_shares, fmv_per_share_on_date_sold, **kwargs):
        fmv = num_shares * fmv_per_share_on_date_sold

        ab = self._cost_per_share * num_shares
        self._ab_with_class.append(self.AB_SUBCLASS(-ab))
        self._num_shares -= num_shares

        gainloss = fmv - ab

        # Related party offset: if this is a sale to an unrelated party of an asset from a related party,
        # you can offset gain by the amount of suspended loss from that other party
        if gainloss > 0:
            gainloss += max(0, -self.suspended_loss)

        # To classify it as LT or ST -- ownership takes place the day after you purchase the stock.
        if self.is_short_term(date):
            return AllGainSale(st_capgain=gainloss)
        return AllGainSale(lt_capgain=gainloss)

    def return_of_capital(self, amount):
        """Allows taxpayer to recognize a return of capital that decreases basis"""
        decrease_per_share = amount / self.num_shares
        [x.return_of_capital(decrease_per_share) for x in self._ab_with_class]
        self._cost_per_share -= decrease_per_share

    def recapture(self, gainloss, cost_recovery=None, to_related_party=False):
        return 0

    def recapture_as_lambda(self):
        return lambda gl: 0

    def depreciate(self, year):
        return 0


class SmallBusinessStock(InvestmentStock):
    """Stock from a small business.  Section 1202 stock and section 1244 stock"""

    def __new__(cls, *args, **kwargs):
        return super(InvestmentStock, cls).__new__(cls)

    def sell(self, date, num_shares, fmv_per_share_on_date_sold, is_corp_owner=False, is_mfj=False, **kwargs):
        # You can exclude 50% of the stock if you have
        normal_gl = super().sell(date, num_shares, fmv_per_share_on_date_sold)
        self.unadjusted_gainloss = normal_gl
        holding_period = self.get_holding_period(date)

        if self.date_acquired <= datetime.date(1993, 8, 10):
            return normal_gl

        # Must be held for over 5 years and be a non-corporate owner to get an exclusion
        if holding_period <= 5 or is_corp_owner:
            return normal_gl

        self.exclusion += 0.5 * normal_gl.long_term_capgain
        normal_gl.long_term_capgain *= 0.5
        return normal_gl

    @property
    def exclusion(self):
        try:
            return self._exclusion
        except AttributeError:
            return 0

    @exclusion.setter
    def exclusion(self, value):
        self._exclusion = value

    @property
    def unadjusted_gainloss(self):
        """Unadjusted gainloss"""
        return self._normal_gl

    @unadjusted_gainloss.setter
    def unadjusted_gainloss(self, value):
        self._normal_gl = value

    @property
    def adjustment_to_gainloss(self):
        """The adjustment needed for form 8949"""
        excluded = self.exclusion
        if hasattr(self, '_non_amt_exclusion'):
            excluded += self._non_amt_exclusion
        return excluded


class Section1202Stock(SmallBusinessStock):
    """
    Section1202 stock is stock from a small business.  If held for over 5 years, noncorp taxpayers
    may exclude up to 100% of the gain from sale/exchange of the stock.

    If you are only excluding part of the stock, then the taxable amount will be taxed at the 28% collectibles rate.
    """

    # TODO: There are some rollover rules for 1202 stock as well that I didn't do.
    #  Basically, if you buy an equivalent w/in 60 days of selling the other stock, you don't have to recognize
    #  the gain on the first stock.

    def sell(self, date, num_shares, fmv_per_share_on_date_sold, is_corp_owner=False, is_mfj=False, **kwargs):
        # Call super on it but skip one level because the 50% exclusion is only for particular circumstances
        normal_gl = super(SmallBusinessStock, self).sell(date, num_shares, fmv_per_share_on_date_sold)
        self.unadjusted_gainloss = normal_gl

        holding_period = self.get_holding_period(date)

        if self.date_acquired <= datetime.date(1993, 8, 10):
            return normal_gl

        # Must be held for over 5 years and be a non-corporate owner to get an exclusion
        if holding_period <= 5 or is_corp_owner:
            return normal_gl

        if self.date_acquired < datetime.date(2009, 2, 18):
            self.exclusion += 0.5 * normal_gl.long_term_capgain
            lt_capgain = normal_gl.long_term_capgain * 0.5
            # Taxed at the 28% collectibles rate
            return AllGainSale(collectibles=lt_capgain)

        elif self.date_acquired < datetime.date(2010, 9, 28):
            self.exclusion += 0.75 * normal_gl.long_term_capgain
            lt_capgain = normal_gl.long_term_capgain * 0.25
            # Taxed at the 28% collectibles rate
            return AllGainSale(collectibles=lt_capgain)

        self._non_amt_exclusion = normal_gl.total
        normal_gl.long_term_capgain = 0
        return normal_gl

    def alt_min_tax_preference_item(self):
        return self.exclusion * 0.07


class Section1244Stock(SmallBusinessStock):
    """Also small business stock.  Follows normal rules and no alt-min preference item"""

    def sell(self, date, num_shares, fmv_per_share_on_date_sold, is_corp_owner=False, is_mfj=False, **kwargs):
        normal_gl = super().sell(date, num_shares, fmv_per_share_on_date_sold, is_corp_owner, is_mfj, **kwargs)
        # If it's a loss and it's section 1244 stock, follows special rules
        if normal_gl < 0:
            return self._loss(normal_gl, is_mfj)
        return normal_gl

    def declare_worthless(self, is_mfj):
        return self._loss(self.ab, is_mfj)

    def _loss(self, loss_amount, is_mfj):
        """Figures out the amount of loss you can take on this stock."""
        if isinstance(loss_amount, AllGainSale):
            loss_amount = sum(
                [loss_amount.short_term_capgain, loss_amount.long_term_capgain, loss_amount.ordinary_income,
                 loss_amount.unrecaptured_section_1250])

        # Figure out ratio of capital contributions to total ownership, which must be separated from the loss
        ratio_of_capital_contr = self.capital_contributions / (self.ab + self.capital_contributions)
        loss_attributable_to_capital = loss_amount * ratio_of_capital_contr
        loss_on_stock = loss_amount - loss_attributable_to_capital

        # Reduce capital contributions by the portion of the loss attributable to capital
        self.capital_contributions -= loss_attributable_to_capital

        # Max loss on stock for any given year is 100_000 if mfj and 50_000 otherwise
        lower_limit = -50_000
        if is_mfj:
            lower_limit = -100_000

        # Loss is bounded by the lower limit
        loss = DoubleBoundedAmount(lower_limit=lower_limit, upper_limit=0, start=loss_on_stock)
        # Its character will be ordinary income.  Please show these numbers on form 4797
        return AllGainSale(ord_income=loss)

    @property
    def capital_contributions(self):
        try:
            return self._capital_contributions
        except AttributeError:
            return 0

    @capital_contributions.setter
    def capital_contributions(self, value):
        self._capital_contributions = value

    def contribute_capital(self, amount):
        """To make a capital contribution to the company"""
        if not hasattr(self, '_capital_contributions'):
            self._capital_contributions = 0

        self.capital_contributions += amount


class OtherSecurity(InvestmentProperty):
    CHARACTER = GLCharacter.CAP_GL

    def __init__(self, ab, fmv, liability=0, dividends_per_year=0, selling_expenses=0, holding_period=0,
                 date_acquired=None):
        self._dividends_per_year = dividends_per_year
        super().__init__(ab=ab, fmv=fmv, liability=liability, selling_expenses=selling_expenses,
                         holding_period=holding_period, date_acquired=date_acquired)

    def get_income(self, **kwargs):
        return self._dividends_per_year


class Bonds(InvestmentProperty):
    """Note: bonds count as boot when a company exchanges them with shareholders instead of stock"""
    CHARACTER = GLCharacter.CAP_GL

    def __init__(self, face_value, cost, fmv, interest, interest_payment_dates: list, years_left, date_acquired,
                 date_issued=None, **kwargs):
        super().__init__(ab=InvestmentUseBasis(cost), fmv=fmv, date_acquired=date_acquired, **kwargs)
        self._face_value = face_value
        self._interest = interest
        self._interest_payment_dates = [x for x in interest_payment_dates]
        self._years_remaining = years_left
        self._date_issued = date_issued

    def get_income(self, date, **kwargs):
        if days_between(date, self.date_acquired) < 365:
            interest_payment_dates = [x for x in self._interest_payment_dates if self.date_acquired <= x <= date]
            num_payments = len(interest_payment_dates)
            return self._interest * self._face_value * num_payments
        return self._interest * self._face_value * len(self._interest_payment_dates)


class CheatyBond(Bonds):
    """This is a class that will ducktype the same but does not actually have the same attributes"""

    def __init__(self, date, interest_paid, bond_premium=0, market_discount=0):
        super().__init__(0, 0, 0, 0, [], 0, date)
        self._interest_this_year = interest_paid
        self.bond_premium = bond_premium
        self.market_discount = market_discount

    def get_income(self, date, **kwargs):
        return self._interest_this_year


class CheatyUSTreasuryBond(Bonds):
    """This is a class that will ducktype the same but does not actually have the same attributes"""

    def __init__(self, date, interest_paid, principal_received, educational_expenses=0, bond_premium=0):
        super().__init__(0, 0, 0, 0, [], 0, date)
        self._interest_this_year = interest_paid
        self._principal_this_year = principal_received
        self._educational = educational_expenses
        self.bond_premium = bond_premium

    def get_income(self, date, **kwargs):
        return self._interest_this_year

    @property
    def total(self):
        return self._interest_this_year + self._principal_this_year

    def was_at_least_24_when_purchased(self):
        return True

    def was_issued_after_1989(self):
        return True

    def get_exclusion(self, date, **kwargs):
        """Rough and tumble calculation"""
        return self._interest_this_year / self.total * self._educational


class TaxExemptBond(Bonds):
    """Municipal bonds, etc."""

    def _would_have_been_income(self, date, **kwargs):
        return super().get_income(date, **kwargs)

    def get_income(self, date, **kwargs):
        return 0


class CheatyTaxExemptBond(CheatyBond):

    def _would_have_been_income(self, date, **kwargs):
        return super().get_income(date, **kwargs)

    def get_income(self, date, **kwargs):
        return 0


class PrivateActivityBonds(TaxExemptBond):
    """
    These are tax exempt bonds issued by or on behalf of a local/state government for providing special
    financing benefits for qualified projects.

    They are tax-exempt for normal taxes but not for AMT.
    """

    def alt_min_tax_preference_item(self, date, **kwargs):
        # Bonds issued in the year 2009 and 2010 are exempt from this
        if self._date_issued is not None and self._date_issued.year in [2009, 2010]:
            return 0
        return self._would_have_been_income(date, **kwargs)


class CheatyPrivateActivityBond(CheatyTaxExemptBond):

    def alt_min_tax_preference_item(self, date, **kwargs):
        # Bonds issued in the year 2009 and 2010 are exempt from this
        if self._date_issued is not None and self._date_issued.year in [2009, 2010]:
            return 0
        return self._would_have_been_income(date, **kwargs)


class FuturesContract(InvestmentProperty):
    """
    Applies to futures contracts, foreign currency contracts, nonequity options, dealer equity options,
    and other exchanges made using the mark-to-market system of accounting
    """

    def __init__(self, cost, date_bought, liability=0):
        super().__init__(cost, cost, liability, date_acquired=date_bought)
        self._fmvs_at_date = {}

    def income_for_tax_year(self, end_tax_year, current_fmv):
        self._fmvs_at_date[end_tax_year] = current_fmv

        end_last_tax_year = datetime.date(month=end_tax_year.month, day=end_tax_year.day, year=end_tax_year.year - 1)
        # Not using try/except because I WANT it to raise an error if you have not adjusted this for the current year
        if self.date_acquired > end_last_tax_year:
            prev_fmv = self.ab
        else:
            prev_fmv = self._fmvs_at_date[end_last_tax_year]

        gainloss = current_fmv - prev_fmv
        # Holding period is divided into 60% LT and 40% ST, regardless of actual hp (section 1256)
        return AllGainSale(lt_capgain=gainloss * .6, st_capgain=gainloss * .4)

    def sell(self, date, selling_price, selling_expenses=0, **kwargs):
        selling_price += self.liability
        if not self._fmvs_at_date:
            prev_fmv = self.ab
        else:
            last_date = max(self._fmvs_at_date.keys())
            prev_fmv = self._fmvs_at_date[last_date]

        self.date_sold = date
        self.selling_expenses = selling_expenses
        self.sales_price = selling_price

        gainloss = selling_price - prev_fmv - selling_expenses
        # holding period is 60% LT, 40% ST
        return AllGainSale(lt_capgain=gainloss * .6, st_capgain=gainloss * .4)

    def recapture(self, gainloss, cost_recovery=None, to_related_party=False):
        return 0

    def recapture_as_lambda(self):
        return lambda gl: 0

    def depreciate(self, year):
        return 0


class LifeInsurancePolicy(InvestmentProperty):
    CHARACTER = GLCharacter.CAP_GL

    def __init__(self, proceeds_per_year, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._proceeds_per_year = proceeds_per_year

    def get_income(self, **kwargs):
        return self._proceeds_per_year


class AccountsReceivable(BusinessProperty, UnRecapturedProperty):
    CHARACTER = GLCharacter.ORDINARY
    pass


class BusinessRealProperty(BusinessProperty):
    CHARACTER = GLCharacter.CAP_GL

    def record_property_tax_invoice(self, id_number, date_billed, amount_billed, date_paid=None, amount_paid=None):
        self.record_expense(id_number, date_billed, amount_billed, description="property taxes",
                            category='real estate tax', date_paid=date_paid, amount_paid=amount_paid)

    def record_property_tax_payment(self, id_number, date, amount):
        self.record_expense_payment(id_number, date, amount)

    @property
    def address(self):
        return self._address

    @address.setter
    def address(self, value):
        self._address = value


class InvestmentRealProperty(InvestmentProperty):
    CHARACTER = GLCharacter.CAP_GL

    def record_property_tax_invoice(self, id_number, date_billed, amount_billed, date_paid=None, amount_paid=None):
        self.record_expense(id_number, date_billed, amount_billed, description="property taxes",
                            category='real estate tax', date_paid=date_paid, amount_paid=amount_paid)

    def record_property_tax_payment(self, id_number, date, amount):
        self.record_expense_payment(id_number, date, amount)

    @property
    def address(self):
        return self._address

    @address.setter
    def address(self, value):
        self._address = value


class BusinessRealResidentialProperty(BusinessRealProperty):
    pass


class InvestmentRealResidentialProperty(InvestmentRealProperty):
    pass


class BusinessRealNonResidentialProperty(BusinessRealProperty):
    pass


class InvestmentRealNonResidentialProperty(InvestmentRealProperty):
    pass


class BusinessPptyOver20YearLife(BusinessProperty):
    """For Land Improvements, Pipelines, Power Generation Equipment, Telephone distribution plants"""
    CHARACTER = GLCharacter.CAP_GL
    pass


class InvestmentPptyOver20YearLife(InvestmentProperty):
    """For Land Improvements, Pipelines, Power Generation Equipment, Telephone distribution plants"""
    CHARACTER = GLCharacter.CAP_GL
    pass


class LandImprovementsBusiness(BusinessPptyOver20YearLife):
    CHARACTER = GLCharacter.CAP_GL
    pass


class LandImprovementsInvestment(InvestmentProperty):
    CHARACTER = GLCharacter.CAP_GL
    pass


class NaturalResourceBusiness(BusinessProperty):
    AB_SUBCLASS = DepletionBasis
    CHARACTER = GLCharacter.SPLIT

    def __init__(self, ab, fmv, resource: str, est_units_recoverable, date_acquired=None, **kwargs):
        ab = self.AB_SUBCLASS(ab, est_units_recoverable, resource,
                              date_put_into_service=date_acquired) if not isinstance(ab, AdjustedBasis) else ab
        super().__init__(ab, fmv, date_acquired=date_acquired, **kwargs)

    def depreciate(self, date, **kwargs):
        total = sum([ab.depreciate(date, **kwargs) for ab in self.ab_obj])
        return total

    def alt_min_tax_preference_item(self, date):
        """AMT requires you to add back in depletion"""
        total = sum([ab.get_depletion(date.year) for ab in self.ab_obj])
        return total


class NaturalResourceInvestment(InvestmentProperty):
    AB_SUBCLASS = DepletionBasis
    CHARACTER = GLCharacter.SPLIT

    def __init__(self, ab, fmv, resource: str, est_units_recoverable, date_acquired=None, **kwargs):
        ab = self.AB_SUBCLASS(ab, est_units_recoverable, resource,
                              date_put_into_service=date_acquired) if not isinstance(ab, AdjustedBasis) else ab
        super().__init__(ab, fmv, date_acquired=date_acquired, **kwargs)

    def depreciate(self, date, **kwargs):
        total = sum([ab.depreciate(**kwargs) for ab in self.ab_obj])
        return total

    def alt_min_tax_preference_item(self, date):
        """AMT requires you to add back in depletion"""
        total = sum([ab.get_depletion(date.year) for ab in self.ab_obj])
        return total


class IntangibleProperty(UnRecapturedProperty):
    AB_SUBCLASS = BusinessUseBasis
    CHARACTER = GLCharacter.SPLIT

    def __init__(self, ab, fmv, description="", use_type=UseType.BUSINESS, liability=0, selling_expenses=0,
                 date_acquired=None, acquired_in_business_acquisition=False, **kwargs):
        super().__init__(ab=ab, fmv=fmv, liability=liability, selling_expenses=selling_expenses,
                         date_acquired=date_acquired, **kwargs)
        self._use_type = use_type
        self.description = description
        self.acquired_in_business_acquisition = acquired_in_business_acquisition

    @property
    def does_holding_period_tack(self):
        return False

    @property
    def category(self):
        return self._use_type


class Section197Intangibles(IntangibleProperty):
    pass


class GoodWill(Section197Intangibles):
    pass


class GoingConcernValue(Section197Intangibles):
    pass


class StartUpOrOrgCosts(IntangibleProperty):
    """For start-up or organizational costs"""
    AB_SUBCLASS = StartupOrgBasis


class StartUp(StartUpOrOrgCosts):
    """Startup costs are costs like deposits on utilities for the shop before you open, creating the website,
    starting up your advertising campaign"""
    CHARACTER = GLCharacter.ORDINARY
    pass


class OrgCosts(StartUpOrOrgCosts):
    """Organizational costs are lawyers fees for incorporation or partnership formation, drafting of contracts,
    and other things required to make the entity actually exist.  However, it does not include stock things (b/c they are
    APIC!)"""
    CHARACTER = GLCharacter.ORDINARY
    pass


class Cash(UnRecapturedProperty):
    AB_SUBCLASS = BusinessUseBasis
    CHARACTER = GLCharacter.ORDINARY

    def __init__(self, amount):
        super().__init__(ab=amount, fmv=amount)

    @property
    def does_holding_period_tack(self):
        return False

    @property
    def category(self):
        return UseType.INVESTMENT

    def __neg__(self):
        return type(self)(-self.ab)


def create_asset(cost, intended_property_class, fs_are_audited=False):
    """Checks the de minimus requirements to see if the asset can be expensed instead of capitalized"""
    limit = 2500
    if fs_are_audited:
        limit *= 2

    if cost <= limit and intended_property_class is not IntangibleProperty:
        return cost
    return intended_property_class(cost, cost)


def compute_basket_purchase(lump_sum_payment, *assets, property_class=BusinessProperty):
    """Remember to file Form 8594"""
    assets = Aggregated(assets)

    total = assets.fmv
    if total >= lump_sum_payment:
        individually = [(asset.fmv / total) * lump_sum_payment for asset in assets]
        new_assets = [property_class(individ_price, individ_price) for individ_price in individually]
    else:
        new_assets = []
        sort_assets_for_residual_method(assets, reverse_list=True)
        # now you treat these as a stack and pop off the back
        lump_sum = lump_sum_payment
        while assets:
            curr_asset = assets.pop()
            if lump_sum > curr_asset.fmv:
                remainder = lump_sum - curr_asset.fmv
                lump_sum -= curr_asset.fmv
            else:
                remainder = lump_sum
                lump_sum = 0
            curr_asset.ab = curr_asset.fmv - remainder

            new_assets.append(curr_asset)

    return new_assets


def sort_assets_for_residual_method(assets_list, reverse_list=False):
    """Sorts the assets so they can be used with the residual method"""
    # There are seven classes of assets.  We must place the assets in order.
    classifications = {Cash: 1,
                       PublicSecurity: 2,
                       OtherSecurity: 3,
                       AccountsReceivable: 3,
                       Inventory: 4,
                       Section197Intangibles: 6,
                       GoodWill: 7,
                       GoingConcernValue: 7
                       }

    def classify(ast):
        for key, val in classifications.items():
            if isinstance(ast, key):
                return val
        return 5

    [setattr(asset, 'order', classify(asset)) for asset in assets_list]

    assets_list.sort(key=lambda x: x.order, reverse=reverse_list)


class PartialStake(object):
    """A partial stake in a piece of property"""

    def __init__(self, ppty, owner, percent_owned, ab=None, fmv=None, liability=None, date_acquired=None):
        self.ppty = ppty
        self.owner = owner
        self.interest = percent_owned
        self._ab = ab
        self._fmv = fmv
        self._liability = liability

        self.depreciation_object = None
        self.depreciation_by_year = {}

        # Some additional things about the asset
        self.selling_expenses = 0
        self.date_acquired = date_acquired

    @property
    def ab(self):
        if self._ab is None:
            return self.ppty.ab * self.interest
        return self._ab

    @property
    def fmv(self):
        if self._fmv is None:
            return self.ppty.fmv * self.interest
        return self._fmv

    @property
    def liability(self):
        if self._liability is None:
            return self.ppty.liability * self.interest
        return self._liability

    def basis(self, **kwargs):
        return self._ab

    # TODO: Do the cost recovery, recapture, and recapture lambda!
    # @property
    # def cost_recovery(self):
    #     return self.ab_obj.cost_recovery
    #
    # def recapture(self, gainloss, **kwargs):
    #     pass
    #
    # def recapture_as_lambda(self):
    #     pass



class Services(object):

    def __init__(self, fair_market_value):
        self._fmv = fair_market_value

    @property
    def fmv(self):
        return self._fmv


