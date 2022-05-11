"""
An IRS decision tree to check for dependents and various other things related to dependents
The Dependents Decision tree has several trees inside it:
    Income Decision Tree (what counts as income)
    Support Decision Tree (what counts as support)
"""
import collections
from enum import Enum, auto
from TaxAlgorithms.dependencies_for_programs.date_funcs import *
from TaxAlgorithms.dependencies_for_programs.filing_status_enum import FilingStatus
from TaxAlgorithms.dependencies_for_programs.irs_decision_tree_superclass import IrsDecisionTree
from TaxAlgorithms.yearly_constants.load_yearly_constants import YearConstants


class TaxPayerRelationships(Enum):
    # Note that these relationships can apply to one's spouse and are not considered ended with divorce or death of
    # spouse

    CHILD = 1
    STEPCHILD = 1
    ADOPTED_CHILD = 1

    SIBLING = 2
    STEPSIBLING = 2
    ADOPTED_SIBLING = 2

    FOSTER_CHILD = 3
    FOSTER_SIBLING = 4

    # Below: includes step-nieces, step-nephews, as well as descendants of siblings who were adopted or foster-siblings
    NIECE = 5
    NEPHEW = 5
    GRAND_NIECE = 5
    GRAND_NEPHEW = 6
    GRANDCHILD = 7

    # Below: other (extended) relatives
    PARENT = 8
    GRANDPARENT = 8
    GREAT_GRANDPARENTS = 8
    UNCLE = 9
    AUNT = 9
    OTHER = 10  # Can include in-laws

    # If they are unrelated or cousins
    UNRELATED = 11
    COUSIN = 12
    SPOUSE = 11

    @classmethod
    def child_only(cls):
        return {cls.CHILD, cls.FOSTER_CHILD, cls.STEPCHILD, cls.ADOPTED_CHILD, cls.ADOPTED_SIBLING, cls.FOSTER_SIBLING,
                cls.SIBLING, cls.STEPSIBLING, cls.NIECE, cls.NEPHEW, cls.GRAND_NEPHEW, cls.GRAND_NIECE, cls.GRANDCHILD}

    @classmethod
    def is_real_child(cls, enum_obj):
        return enum_obj.value in [1, 3]


class IncomeIrsDecisionTree(object):
    """What counts as income for the dependent relative tests"""

    def __init__(self):
        self.tree = IrsDecisionTree()
        self._build_tree()

    def _build_tree(self):
        self.tree.add_branch(parent_node='root', branch=True, identifier='is_income',
                             description='is it income? (if False, will be considered expense)',
                             if_func=lambda x, **kwargs: x.amount > 0,
                             )
        # For expenses
        self.tree.add_branch(parent_node='is_income', branch=False, identifier='is_cogs',
                             description='is the expense a cost of goods sold for a trade/business?',
                             if_func=lambda x, **kwargs: x.category == 'cogs')
        self.tree.add_branch(parent_node='is_cogs', branch=True, identifier='include',
                             description='include in gross income')
        self.tree.add_branch(parent_node='is_cogs', branch=False, identifier='dont_include',
                             description='do not include in gross income')

        # For income
        self.tree.add_branch(parent_node='is_income', branch=True, identifier='is_tax_exempt',
                             description='is it tax exempt income (ex. municipal bond)?',
                             if_func=lambda x, **kwargs: x.category == 'tax_exempt')
        self.tree.connect(parent_node='is_tax_exempt', branch=True, child_identifier='dont_include')
        self.tree.add_branch(parent_node='is_tax_exempt', branch=False, identifier='is_social_security',
                             description='is it a social security benefit (with no additional income received)?',
                             if_func=lambda x, **kwargs: x.category == 'social_security' or 'ssa' in x.description)
        self.tree.connect('is_social_security', True, 'dont_include')
        # Everything else is going to be included.  Some of the categories that are specifically included are:
        # - unemployment compensation
        # - rental income (NOT offset by rental expenses)
        # - net sales from a Trade or Business (offset by COGS but nothing else)
        # - other income from a Trade or Business (not offset by any expenses)
        self.tree.connect('is_social_security', False, 'include')

    def traverse(self, all_line_items: list):
        """
        Takes a list of line items and traverses the tree with them.
        Line items require the attributes: 'category', 'description', and 'amount'
        :return: total amount included in gross income
        """
        self.tree.traverse_store(all_line_items, 'x')
        return sum([x.amount for x in self.tree.nodes['include'].storage])



class SupportPurpose(Enum):
    HH = auto()
    DEPENDENT_CHILD = auto()
    DEPENDENT_RELATIVE = auto()
    NONE = auto()


class Support(object):
    """
    Checks on support percents for different tests.
    Each instance is support for ONE INDIVIDUAL.  The support items passed through can be prorated if it is
    included in the parameters that there's more than one person taking advantage of the item.
    """
    ARE_NOT_SUPPORT = {'scholarship', 'tax', 'life insurance'}  # Also, no amounts paid in arrears
    # Note that purchase of capital items such as furniture, appliances, and cars CANNOT be included in support if they
    # are purchased for personal/family reasons AND they benefit the entire household

    # If an item of support is not in cash, the amount of the item is usually its cost (if purchased) or FMV
    # (if otherwise obtained)

    FOR_HH = {'food_consumed_in_home', 'property_tax', 'mortgage_interest', 'rent', 'utilities', 'home_upkeep',
              'home_repair', 'property_insurance'}
    FOR_DEPENDENT_CHILD = FOR_HH.union(
        {'food_consumed_out_of_home', 'clothes', 'medical', 'dental', 'insurance', 'education', 'childcare',
         'daycare', 'vacation', 'transportation'}
    )
    FOR_DEPENDENT_RELATIVE = FOR_DEPENDENT_CHILD.union(
        {'welfare_benefits', 'social_security_benefits', 'money', 'items', 'money_spent_on_items'}
    )

    SUPPORT_TYPES = FOR_DEPENDENT_RELATIVE
    BY_PURPOSE = {SupportPurpose.HH: FOR_HH, SupportPurpose.DEPENDENT_CHILD: FOR_DEPENDENT_CHILD,
                  SupportPurpose.DEPENDENT_RELATIVE: FOR_DEPENDENT_RELATIVE, SupportPurpose.NONE: SUPPORT_TYPES}

    SuppItem = collections.namedtuple('SuppItem', ['payer', 'category', 'amount', 'date_paid', 'date_due'])

    def __init__(self, recipient):
        self._decision_tree = SupportDecisionTree()
        self.recipient = recipient
        self.clear()

    def clear(self):
        self._support = {x: {} for x in self.SUPPORT_TYPES}
        self._totals = {x: [] for x in SupportPurpose}

        self._by_taxpayer = {}

    @classmethod
    def is_support(cls, supp_item):
        """Checks for an obvious sign that this is not support"""
        for text in cls.ARE_NOT_SUPPORT:
            if text in supp_item.category:
                return False
        return True

    def transfer_support(self, new_entity):
        """Transfers the support to a new entity"""
        if self.recipient in self._by_taxpayer:
            self._by_taxpayer[new_entity] = self._by_taxpayer[self.recipient]
            del self._by_taxpayer[self.recipient]
        for item, values in self._support.items():
            if self.recipient in values:
                values[new_entity] = values[self.recipient]
                del values[self.recipient]

    def _get_taxpayer(self, taxpayer):
        """Switches the taxpayer to the wrapped object for the recipient, to allow easy transfer later"""
        if taxpayer is self.recipient:
            return self.recipient
        return taxpayer

    def add_food_support(self, taxpayer_who_paid, amount_paid, consumed_in_home: bool, date_paid,
                         date_should_have_been_paid=None, num_people_using=1):
        if consumed_in_home:
            category = 'food_consumed_in_home'
        else:
            category = "food_consumed_out_of_home"
        self.add_support(category, taxpayer_who_paid, amount_paid, date_paid, date_should_have_been_paid,
                         num_people_using)

    def add_support(self, category, taxpayer_who_paid, amount_paid, date_paid, date_should_have_been_paid=None,
                    num_people_using=1):
        date_should_have_been_paid = date_should_have_been_paid or date_paid
        taxpayer_who_paid = self._get_taxpayer(taxpayer_who_paid)

        # If it's not support, it'll be caught by the decision tree
        item = self.SuppItem(taxpayer_who_paid, category, amount_paid / num_people_using, date_paid,
                             date_should_have_been_paid)
        try:
            self._support[category].setdefault(taxpayer_who_paid, [])
            self._support[category][taxpayer_who_paid].append(item)
        except KeyError:
            self._support[category] = {taxpayer_who_paid: [item]}
            self.SUPPORT_TYPES.add(category)

        # Record Totals
        self._by_taxpayer.setdefault(taxpayer_who_paid, {x: [] for x in SupportPurpose})
        for purpose, lst in self.BY_PURPOSE.items():
            if category in lst:
                self._totals[purpose].append(item)
                self._by_taxpayer[taxpayer_who_paid][purpose].append(item)

    def add_support_not_paid_in_cash(self, category, taxpayer_who_paid, fmv, date):
        """For if the item was not paid for in cash"""
        self.add_support(category, taxpayer_who_paid, fmv, date, date)

    def percent_paid(self, end_tax_year, taxpayer, support_purpose=SupportPurpose.NONE):
        """Gets the percent of support paid by an individual"""
        try:
            self._decision_tree.clear()
            paid = self._decision_tree.traverse(end_tax_year, self._by_taxpayer[taxpayer][support_purpose])
            self._decision_tree.clear()
            total = self._decision_tree.traverse(end_tax_year, self._totals[support_purpose])
            return paid / total
        except KeyError:
            return 0

    def total_support(self, end_tax_year, purpose=SupportPurpose.NONE):
        self._decision_tree.clear()
        total = self._decision_tree.traverse(end_tax_year, self._totals[purpose])
        return total


class SupportDecisionTree(object):
    """
    This decision tree is meant to decide whether or not an item SHOULD BE included in support.
    The actual Support object should use this to help it make decisions as pertain to the item in question
    """
    APPLIANCES = ['microwave', 'oven', 'washer', 'washing machine', 'dryer', 'stove', 'dishwasher',
                  'dishwashing machine', 'refrigerator', 'fridge', 'freezer']

    def __init__(self):
        self._year_start = None
        self._year_end = None

        self.tree = IrsDecisionTree()
        self._build_tree()

    def clear(self):
        for node in self.tree.nodes.values():
            node.storage.clear()

    def _build_tree(self):
        self.tree.add_branch('root', True, identifier='is_correct_period',
                             description='was it paid in the current tax year (and not in arrears)?',
                             if_func=lambda x, **kwargs: (self._year_start <= x.date_paid <= self._year_end and
                                                          self._year_start <= x.date_due <= self._year_end))
        self.tree.add_branch('is_correct_period', False, identifier='not_support', description="Not support")
        self.tree.add_branch('is_correct_period', True, identifier='is_in_nonsupport_category',
                             description="Is it a life insurance premium, a scholarship, or taxes?",
                             if_func=lambda x, **kwargs: not Support.is_support(x))
        self.tree.connect('is_in_nonsupport_category', True, 'not_support')
        self.tree.add_branch('is_in_nonsupport_category', False, identifier='is_capital_item',
                             description='is it a capital item (appliance, furniture, car)?',
                             if_func=lambda x, **kwargs: x.category in self.APPLIANCES or x.category in
                                                         ['car', 'furniture'])
        self.tree.add_branch('is_capital_item', False, 'is_support', 'this counts as support')

        # These will be assumed to be True for now, but could be modified to be actual decision branches
        self.tree.add_branch('is_capital_item', True, identifier='is_personal_use_item',
                             description='was the item purchased for personal or family reasons?',
                             if_func=lambda x, **kwargs: True)
        self.tree.add_branch('is_personal_use_item', True, identifier='does_benefit_whole_household',
                             description='Does the item benefit the entire household?',
                             if_func=lambda x, **kwargs: True)
        self.tree.connect('is_personal_use_item', False, 'is_support')
        self.tree.connect('does_benefit_whole_household', False, 'is_support')
        self.tree.connect('does_benefit_whole_household', True, 'not_support')

    def traverse(self, end_tax_year, items):
        self._year_end = end_tax_year
        self._year_start = back_one_year(end_tax_year, less_one_day=True)

        self.tree.traverse_store(items, 'x')
        return sum([x.amount for x in self.tree.nodes['is_support'].storage])


class MustUseSupportTestTree(object):
    """A tree to determine whether or not to use the decision tree to do the support test in the first place"""

    class Results(Enum):
        IS_DEPENDENT = auto()
        IS_NOT_DEPENDENT = auto()
        DO_TEST = auto()
        SKIP_TEST = auto()

    def __init__(self):
        self.tree = IrsDecisionTree()
        self._build_tree()

    def _build_tree(self):
        self.tree.add_branch('root', True, 'is_divorced_or_separated',
                             'is the taxpayer divorced or separated from spouse?',
                             if_func=lambda person, taxpayer, **kwargs: (
                                     person.relationship_to_taxpayer is TaxPayerRelationships.CHILD and
                                     person.are_parents_separated is True
                             ))
        self.tree.add_branch('is_divorced_or_separated', False, 'do_test', 'Support test required')
        self.tree.add_branch('is_divorced_or_separated', True, 'have_provided_most_support',
                             'have you and your ex provided (between the both of you) over 50% of the support?',
                             if_func=lambda person, taxpayer, taxpayers_ex, end_tax_year, **kwargs: (
                                     person.support.percent_paid(taxpayer, end_tax_year) +
                                     person.support.percent_paid(taxpayers_ex, end_tax_year) > .5
                             ))
        self.tree.connect('have_provided_most_support', False, 'do_test')

        # For the rest of these, I will say True for now but they should be modified so applicable
        self.tree.add_branch('have_provided_most_support', True, 'have_had_custody',
                             'have you and your ex (between you both) had custody of the child for over '
                             '50% of the year?',
                             if_func=lambda **kwargs: True)

        self.tree.add_branch('have_had_custody', True, 'have_lived_apart',
                             'have you and your ex lived apart for the last half-year?',
                             if_func=lambda **kwargs: True)
        self.tree.add_branch('have_lived_apart', True, 'have_multiple_support_agreement',
                             'do you and your ex have a multiple support agreement (Form 2120)?',
                             if_func=lambda **kwargs: False)

        self.tree.connect('have_had_custody', False, 'do_test')
        self.tree.connect('have_lived_apart', False, 'do_test')
        self.tree.add_branch('have_multiple_support_agreement', False, 'skip_test', 'you can skip the support test')

        self.tree.add_branch('have_multiple_support_agreement', True, 'are_you_recipient_on_agreement',
                             'does the agreement confirm that you should claim this dependent?',
                             if_func=lambda **kwargs: False)
        self.tree.add_branch('are_you_recipient_on_agreement', True, 'is_dependent', 'you may claim dependent')
        self.tree.add_branch('are_you_recipient_on_agreement', False, 'is_not_dependent', 'you may not claim the '
                                                                                          'dependent')

    def traverse(self, taxpayer, taxpayers_ex, person, end_tax_year):
        result = self.tree.get_final_node(taxpayer=taxpayer, taxpayers_ex=taxpayers_ex, person=person,
                                          end_tax_year=end_tax_year)
        return self.Results[result.upper()]


class Person(object):
    """To compile information about the person that will help assess if they are a dependent"""

    def __init__(self, first_name, last_name, middle_initial, relationship_to_taxpayer: TaxPayerRelationships,
                 date_of_birth, support_obj=None, months_enrolled_at_school=10, nationality='US', residency='US',
                 is_mfj=False, is_filing_only_for_refund=False, tin=None, is_permanently_disabled=False):
        self._first_name = first_name
        self._last_name = last_name
        self._middle_initial = middle_initial

        self.date_of_birth = date_of_birth
        self.are_parents_separated = False

        self.nationality = nationality
        self.residency = residency
        self.is_mfj = is_mfj
        self.is_filing_only_for_refund = is_filing_only_for_refund
        self.tin = tin
        self.is_permanently_disabled = is_permanently_disabled

        if not isinstance(relationship_to_taxpayer, TaxPayerRelationships):
            raise TypeError("Must be TaxPayerRelationships class")
        self.relationship_to_taxpayer = relationship_to_taxpayer

        # Addresses is a dictionary of {year: {address(str): percent of year spent there(float)}}
        self.addresses = {}
        # Months enrolled at school during the year
        self.months_enrolled_at_school = months_enrolled_at_school
        self.support = support_obj if support_obj is not None else Support(self)

    def __hash__(self):
        return hash(self.name)

    @property
    def name(self):
        middle_init = ' ' + self._middle_initial if self._middle_initial else ''
        return f"{self._first_name}{middle_init} {self._last_name}"

    def add_address(self, year, address, percent_of_time_living_there):
        """
        :param year: tax year this applies to
        :param address: str -- usually.  However, if you pass through the taxpayer class object here,
            it will be assumed that you mean that this person lived with that taxpayer at their primary residence
            for this percent of the time.
        :param percent_of_time_living_there: float.  Decimal percentage.  Ex 50% = 0.5
        """
        self.addresses.setdefault(year, {})
        if isinstance(address, str) or hasattr(address, 'zipcode'):
            self.addresses[year][address] = percent_of_time_living_there
        else:
            taxpayer = address
            self.addresses[year][taxpayer.address] = percent_of_time_living_there

    def percent_of_time_at_taxpayers_residence(self, year, taxpayer):
        try:
            return self.addresses[year][taxpayer.address]
        except KeyError:
            return 0

    @classmethod
    def is_dependent(cls, end_tax_year, taxpayer, maybe_dependent, relationship, tin,
                     is_for_medical_expense_deduction=False,
                     spouse_number=1, is_filing_mfj_only_for_refund=False):
        """Checks if the other person is a dependent"""
        is_mfj = maybe_dependent.filing_status.name.lower() == 'mfj'
        new_obj = cls(maybe_dependent.first_name(spouse_number=spouse_number),
                      maybe_dependent.last_name(spouse_number=spouse_number),
                      maybe_dependent.middle_initial(spouse_number=spouse_number),
                      relationship, maybe_dependent.get_dob(spouse_number=spouse_number),
                      nationality=maybe_dependent.nationality, residency=maybe_dependent.country_of_residence,
                      is_mfj=is_mfj, is_filing_only_for_refund=is_filing_mfj_only_for_refund, tin=tin)
        if not new_obj._can_be_dependent(is_for_medical_expense_deduction):
            return False
        if new_obj.is_dependent_child(end_tax_year, taxpayer, is_for_medical_expense_deduction):
            return True
        if new_obj.is_qualifying_relative(end_tax_year, taxpayer,
                                          list(maybe_dependent._income_items.iter_income(end_tax_year)),
                                          is_for_medical_expense_deduction):
            return True
        return False

    def _can_be_dependent(self, for_medical_expenses=False):
        """
        Checks if this person CAN be a dependent or if instantiation of the Dependents Mixin will immediately
        crash the program (by design -- I told it to crash).
        """
        # Must have a taxpayer ID number or an SSN or other ID number used for tax purposes
        if self.tin is None:
            return False
        # Must be a resident/national/citizen of mexico, canada, or US
        qualifying = {'US', 'Mexico', 'Canada'}
        if self.nationality not in qualifying and self.residency not in qualifying:
            return False
        # Cannot file MFJ (unless you are just doing it for the refund)
        # (This criteria is waived if you are trying to determine dependency for sake of the Sched A Medical Deduction)
        if not for_medical_expenses:
            if self.is_mfj and not self.is_filing_only_for_refund:
                return False
        return True

    def is_dependent_child(self, end_tax_year, taxpayer, is_for_medical_deduction=False, **kwargs):
        """
        Checks if this person is a dependent child
        :param end_tax_year: Date.
        :param taxpayer: USTaxpayer Class
        :param is_for_medical_deduction: if this is being run to determine dependency for the sake of the itemized
                medical deduction on Schedule A, then this parameter should be True.
        :return: bool
        """
        # Test 1: Relationship - Must be child, sibling, or sibling/child's descendant
        if self.relationship_to_taxpayer not in TaxPayerRelationships.child_only():
            return False

        # Test 2: Age - Must be under 24. If 19+, must be enrolled in school/farm training pgm at least 5 months
        age = get_age(self.date_of_birth, end_tax_year)
        if age >= 24:
            return False
        if 19 <= age < 24 and self.months_enrolled_at_school < 5:
            return False

        # Test 3: Principal Residence - must have same principal residence as taxpayer for over 1/2 of year
        percent_of_time_living_at_taxpayers_residence = self.percent_of_time_at_taxpayers_residence(
            end_tax_year.year, taxpayer)

        if percent_of_time_living_at_taxpayers_residence <= .5:
            return False

        # Test 4: Not self-supporting - child must NOT have provided over 1/2 his/her own support
        percent_of_own_support_paid = self.support.percent_paid(end_tax_year=end_tax_year, taxpayer=self,
                                                                support_purpose=SupportPurpose.DEPENDENT_CHILD)
        if percent_of_own_support_paid > .5:
            return False

        return self._can_be_dependent(is_for_medical_deduction)

    def is_qualifying_relative(self, end_tax_year, taxpayer, income_line_items_of_person,
                               is_for_medical_deduction=False, **kwargs):
        """
        Checks if they are a qualifying relative
        :param end_tax_year:
        :param taxpayer:
        :param income_line_items_of_person: This must be an iterable of a bunch of line items representing income and
                expenses of a person.  General overview is below.  But these will be fed into a decision tree to figure
                out what counts and what does not.

            Overall:
            For rental income:
                Only the income.  No deductions can be taken.
            For Business income:
                Business revenue - COGS + other business income
            For unemployment compensation:
                Include it
            For social security benefits:
                Exclude it
        :param is_for_medical_deduction: if this is being run to determine dependency for the sake of the itemized
                medical deduction on Schedule A, then this parameter should be True.
        :return:
        """
        # Test 4: Is not qualifying child
        if self.is_dependent_child(end_tax_year=end_tax_year, taxpayer=taxpayer,
                                   is_for_medical_deduction=is_for_medical_deduction):
            return False
        # (Also, can't be spouse)
        if self.relationship_to_taxpayer is TaxPayerRelationships.SPOUSE:
            return False

        # Test 1: Relationship or residence (can be one or the other)
        residence_test_passed = False
        relationship_test_passed = False

        percent_of_time_living_at_taxpayers_residence = self.percent_of_time_at_taxpayers_residence(
            end_tax_year.year, taxpayer)

        if percent_of_time_living_at_taxpayers_residence == 1:
            residence_test_passed = True

        if self.relationship_to_taxpayer is not TaxPayerRelationships.UNRELATED:
            relationship_test_passed = True

        # If both these tests fail, then this first test fails and they are not a dependent relative
        if not residence_test_passed and not relationship_test_passed:
            return False

        # Test 2: Gross Income
        # (Note that gross income test is always required UNLESS it's for the medical deduction on Schedule A)
        if not is_for_medical_deduction:
            limit = YearConstants().dependent_relative_gross_income_limit[f"{end_tax_year.year}"]
            decision_tree = IncomeIrsDecisionTree()
            all_income_person_received = decision_tree.traverse(income_line_items_of_person)

            if all_income_person_received >= limit:
                return False

        # Test 3: Support - taxpayer must provide over 50% of total economic support of relative
        percent_support_paid = self.support.percent_paid(end_tax_year=end_tax_year, taxpayer=taxpayer,
                                                         support_purpose=SupportPurpose.DEPENDENT_RELATIVE)
        if percent_support_paid <= .5:
            return False

        return self._can_be_dependent()

    def is_qualifying_person_for_child_and_dependent_care_credit(
            self, end_tax_year, taxpayer, is_person_mentally_or_physically_incapacitated, is_taxpayer_employed,
            **kwargs):
        """Checks if this is a qualifying person for the sake of the Child and dependent care credit"""
        if not is_taxpayer_employed:
            return False
        is_dependent_child = self.is_dependent_child(end_tax_year, taxpayer)
        age = get_age(self.date_of_birth, end_tax_year)

        if is_dependent_child and age < 13 and self.relationship_to_taxpayer is TaxPayerRelationships.CHILD:
            return True

        if not is_person_mentally_or_physically_incapacitated and age >= 13:
            return False

        percent_of_time_living_at_taxpayers_residence = self.percent_of_time_at_taxpayers_residence(
            end_tax_year.year, taxpayer)

        if percent_of_time_living_at_taxpayers_residence <= .5:
            return False
        return True

    def is_eic_qualified_child(self, end_tax_year, taxpayer, list_of_others_claiming_person,
                               relationship_of_person_to_others_listed, **kwargs):
        """Checks for the EIC"""
        okay_enum_values = [1, 2, 3, 4, 5, 6, 7]
        # Relationship test:
        if self.relationship_to_taxpayer.value not in okay_enum_values:
            return False

        # Age test
        # If they are permanently disabled at any time during the year, then they pass this test
        if not self.is_permanently_disabled:
            child_age = get_age(self.date_of_birth, end_tax_year)

            if child_age >= 24:
                return False
            if 19 <= child_age < 24 and self.months_enrolled_at_school < 5:
                return False

            # Get min age of you and your spouse
            your_age = taxpayer.age(end_tax_year, spouse_number=1)
            your_age = min(your_age, taxpayer.age(end_tax_year, spouse_number=2))

            if child_age > your_age:
                return False

        # Joint return test - must not be filing a joint return with anyone else (or only for refund)
        if self.is_mfj and not self.is_filing_only_for_refund:
            return False

        # Residency test: must have lived with you over half the year
        percent_of_time_living_at_taxpayers_residence = self.percent_of_time_at_taxpayers_residence(
            end_tax_year.year, taxpayer)

        if percent_of_time_living_at_taxpayers_residence <= .5:
            return False

        # Must have ssn/tin
        if not self.tin:
            return False

        if list_of_others_claiming_person:
            return self._tiebreaker_rules(end_tax_year, taxpayer, list_of_others_claiming_person,
                                          relationship_of_person_to_others_listed)
        return True

    def _tiebreaker_rules(self, end_tax_year, taxpayer, list_of_others_claiming, relationship_of_others_claiming):
        """
        Tiebreaker rules to determine who can claim the child as their dependent/qualified person.
        This comes up for:
            1. The child tax credit, credit for other dependents, and additional child tax credit.
            2. Head of household filing status.
            3. The credit for child and dependent care expenses.
            4. The exclusion for dependent care benefits.
            5. The EIC.
        For all of the above, only 1 person can claim the child.  For some, there can be an agreement.
        For the EIC, there is this.
        :param end_tax_year: end of the tax year in question
        :param taxpayer: the taxpayer we are filing the return for
        :param list_of_others_claiming: This is a list of Taxpayer class objects.  All other persons claiming the child
            as their dependent
        :param relationship_of_others_claiming: A list of enums of TaxpayerRelationship.  Its indexing must match the
            first list so that each taxpayer listed above has a relationship here.
        :return: boolean value of whether or not the taxpayer can claim this person
        """
        tpyr_relationships = [(taxpayer, self.relationship_to_taxpayer)]
        tpyr_relationships.extend([(x, y) for x, y in zip(list_of_others_claiming, relationship_of_others_claiming)])

        # If only one of the persons is the child's parent, the child is treated as the qualifying child of the parent.
        parents = []
        for tpyr, relship in tpyr_relationships:
            if relship is TaxPayerRelationships.CHILD:
                parents.append(tpyr)

        if len(parents) == 1:
            return parents[0] is taxpayer

        # If the parents don't file a joint return together but both
        # parents claim the child as a qualifying child, the IRS
        # will treat the child as the qualifying child of the parent
        # with whom the child lived for the longer period of time
        # during the year.
        if len(parents) > 1:
            max_time = -float('inf')
            time_with_parents = []
            for parent in parents:
                time = self.percent_of_time_at_taxpayers_residence(end_tax_year.year, parent)
                if time < max_time or time <= .5:
                    continue
                if time > max_time:
                    max_time = time
                    time_with_parents = []

                time_with_parents.append(parent)

            if len(time_with_parents) == 1:
                parent = time_with_parents[0]
                return parent is taxpayer

            # If the child lived with each parent for
            # the same amount of time, the IRS will treat the child as
            # the qualifying child of the parent who had the higher
            # adjusted gross income (AGI) for the year.
            if len(time_with_parents) > 1:
                parent = max(parents, key=lambda x: x.get_agi(end_tax_year))
                return parent is taxpayer

        # If no parent can claim the child as a qualifying child,
        # the child is treated as the qualifying child of the person
        # who had the highest AGI for the year.
        tpyr_who_gets_qualifier = max(list_of_others_claiming, key=lambda x: x.get_agi(end_tax_year))

        # TODO: There's one more criteria that I didn't do (see comment below)
        # Didn't do this one but:
        # If a parent can claim the child as a qualifying child but no parent does so claim the child, the child is
        # treated as the qualifying child of the person who had the highest AGI for the year, but only if that
        # person's AGI is higher than the highest AGI of any of the child's parents who can claim the child.
        return tpyr_who_gets_qualifier is taxpayer

    def create_dependent(self, dependent_class, taxpayer_dependent_on, end_tax_year,
                         income_line_items_of_person=()):
        """Instantiates the dependent class using the information from this class, and adds the dependent to the
        taxpayer's dependents area"""
        is_dependent_child = False
        is_dependent_relative = False
        if not self.is_dependent_child(end_tax_year=end_tax_year, taxpayer=taxpayer_dependent_on):
            if not self.is_qualifying_relative(end_tax_year, taxpayer_dependent_on, income_line_items_of_person):
                raise TypeError("Not a dependent")
            else:
                is_dependent_relative = True
        else:
            is_dependent_child = True

        filing_status = FilingStatus.MFJ if self.is_mfj else FilingStatus.SINGLE
        dep = dependent_class(tin=self.tin, filing_status=filing_status,
                              is_only_filing_to_claim_refund=self.is_filing_only_for_refund,
                              support_obj=self.support, first_name=self._first_name, last_name=self._last_name,
                              middle_initial=self._middle_initial, date_of_birth=self.date_of_birth,
                              principal_residence=self.addresses, is_dependent_child=is_dependent_child,
                              relationship=self.relationship_to_taxpayer, residence=self.residency
                              )
        taxpayer_dependent_on.dependents.append(dep)
        dep.person = self
        dep._ssn = self.tin

        dep.add_income_line_items(income_line_items_of_person)
        return dep


class IsHeadOfHousehold(object):
    """A decision tree to see if you qualify as head of household"""

    def __init__(self):
        self.tree = IrsDecisionTree()
        self._build_tree()

    def _build_tree(self):
        def is_married_eoy(end_of_tax_year, marriage_date=None, divorce_date=None, **kwargs):
            if marriage_date is None or marriage_date > end_of_tax_year:
                return False
            if divorce_date is None and marriage_date <= end_of_tax_year:
                return True
            if end_of_tax_year <= divorce_date:
                return False
            return True

        def is_dependent(end_of_tax_year, qual_person, **kwargs):
            if qual_person.is_dependent_child(end_of_tax_year, **kwargs):
                return True
            return qual_person.is_qualifying_relative(end_of_tax_year, **kwargs)

        self.tree.add_branch('root', True, 'is_married_on_final_day',
                             'are you legally "married" on the final day of the tax year?',
                             if_func=is_married_eoy)

        self.tree.add_branch('is_married_on_final_day', True, 'is_spouse_nonresident_alien',
                             'is your spouse a nonresident alien?',
                             if_func=lambda taxpayers_spouse, **kwargs: taxpayers_spouse.is_nonresident_alien)
        self.tree.add_branch('is_spouse_nonresident_alien', True, 'is_unmarried',
                             'You are unmarried for purposes of the Head of Household requirement',
                             if_func=lambda **kwargs: True)

        # Below, there is a list of things you must do in order to qualify as HH if you are married.
        # ALL must be True to be able to file as HH
        self.tree.add_branch('is_spouse_nonresident_alien', False, 'is_separated',
                             'Have you been separated from your spouse for at least 6 months?',
                             if_func=lambda end_of_tax_year, date_of_separation, **kwargs: (
                                     end_of_tax_year.month - date_of_separation.month + 1 >= 6))
        self.tree.add_branch('is_separated', False, 'not_hh', 'Cannot file as Head of Household')
        self.tree.add_branch('is_separated', True, 'do_file_separately',
                             "Do you and your spouse file separate returns?",
                             if_func=lambda file_separately, **kwargs: file_separately)
        self.tree.connect('do_file_separately', False, 'not_hh')
        self.tree.add_branch('do_file_separately', True, 'provide_over_half_expenses_married',
                             'Do you provide over 1/2 the expenses of running a household?',
                             if_func=lambda end_of_tax_year, qual_person, taxpayer, **kwargs: (
                                     qual_person.support.percent_paid(end_of_tax_year, taxpayer,
                                                                      SupportPurpose.HH) > .5))
        self.tree.add_branch('provide_over_half_expenses_married', True, 'is_principal_residence_married',
                             "Is your residence the principal residence of the qualified individual for over 1/2 the "
                             "year?",
                             if_func=lambda end_of_tax_year, qual_person, taxpayer, **kwargs: (
                                     qual_person.percent_of_time_at_taxpayers_residence(end_of_tax_year.year,
                                                                                        taxpayer) > .5))
        self.tree.add_branch('is_principal_residence_married', True, 'is_dependent', "Is the person your dependent?",
                             if_func=is_dependent)

        # If all of the above are true, then the only thing left is to see if they are a qualifying individual
        self.tree.connect('provide_over_half_expenses_married', False, 'not_hh')
        self.tree.connect('is_principal_residence_married', False, 'not_hh')

        # Now, must check if the individual is qualified
        self.tree.add_branch('is_married_on_final_day', False, 'is_household_maintained',
                             'Do you provide over 50% of the costs of running the household for the qualifying '
                             'individual?',
                             if_func=lambda end_of_tax_year, qual_person, taxpayer, **kwargs: (
                                     qual_person.support.percent_paid(end_of_tax_year, taxpayer,
                                                                      SupportPurpose.HH) > .5))
        self.tree.connect('is_household_maintained', False, 'not_hh')

        self.tree.add_branch('is_household_maintained', True, 'check_if_qualifying',
                             'Must now check if individual qualifies.',
                             if_func=lambda **kwargs: True)
        # Hook this one (from above) up to the check for a qualified individual
        # TODO: There's a check for a dependency agreement.  This should be eliminated from the HH check.
        self.tree.connect('is_principal_residence_married', True, 'check_if_qualifying')

        # Now we need to know who the qualified individual is, because there are different rules.
        # Parents:
        self.tree.add_branch('check_if_qualifying', True, 'is_parent',
                             'Is the qualifying individual a parent?',
                             if_func=lambda qual_person: qual_person.relationship_to_taxpayer is
                                                         TaxPayerRelationships.PARENT)
        self.tree.add_branch('is_parent', True, 'is_dependent', 'Is the qualifying individual your dependent?',
                             if_func=is_dependent)
        self.tree.add_branch('is_dependent', True, 'is_hh', 'You can file as head of household')
        self.tree.connect('is_dependent', False, 'not_hh')

        # Children
        self.tree.add_branch('is_parent', False, 'is_child', 'Is qualifying person your child?',
                             if_func=lambda qual_person: qual_person.relationship_to_taxpayer is
                                                         TaxPayerRelationships.CHILD)
        self.tree.add_branch('is_child', True, 'is_qual_person_married', 'Is the qualifying person married?',
                             if_func=lambda qual_person: qual_person.is_mfj)
        self.tree.connect('is_qual_person_married', False, 'is_hh')
        self.tree.connect('is_qual_person_married', True, 'is_dependent')

        # Everyone else
        self.tree.add_branch('is_child', False, 'is_resident',
                             'Is their primary residence same as yours for over 1/2 the year?',
                             if_func=lambda end_of_tax_year, qual_person, taxpayer, **kwargs: (
                                     qual_person.percent_of_time_at_taxpayers_residence(end_of_tax_year.year,
                                                                                        taxpayer) > .5))
        self.tree.add_branch('is_resident', True, 'is_relative', 'Is qualifying person related?',
                             if_func=lambda qual_person: qual_person.relationship_to_taxpayer not in [
                                 TaxPayerRelationships.SPOUSE, TaxPayerRelationships.COUSIN,
                                 TaxPayerRelationships.UNRELATED
                             ])
        self.tree.connect('is_relative', True, 'is_dependent')
        self.tree.connect('is_resident', False, 'not_hh')
        self.tree.connect('is_relative', False, 'not_hh')

    def traverse(self, taxpayer, qual_person, taxpayers_spouse=None, marriage_date=None, divorce_date=None,
                 separation_date=None, file_separately=False):
        kwrgs = {'taxpayer': taxpayer, 'qual_person': qual_person, 'taxpayers_spouse': taxpayers_spouse,
                 'marriage_date': marriage_date, 'divorce_date': divorce_date,
                 'separation_date': separation_date, 'file_separately': file_separately}
        final_node = self.tree.get_final_node(**kwrgs)
        if final_node == 'not_hh':
            return False
        elif final_node == 'is_hh':
            return True
        raise ValueError(f"Something went wrong.  Value of final node is {final_node}")
