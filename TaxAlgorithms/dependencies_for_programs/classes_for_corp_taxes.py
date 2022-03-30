"""
Contains E&P, AEP, corporation classes, and others
"""
from abc import ABC, abstractmethod
from TaxAlgorithms.dependencies_for_programs.aggregated_list_class import Aggregated
from TaxAlgorithms.dependencies_for_programs.classes_stock import PartialShares
from TaxAlgorithms.dependencies_for_programs.constructive_ownership_shareholders import NonIndividualShareholder
from TaxAlgorithms.yearly_constants.load_yearly_constants import YearConstants





class EarningsAndProfits(ABC):
    def __init__(self):
        self._earnings_and_profits = 0
        self._amount = None

    @property
    def earnings_and_profits(self):
        return self._earnings_and_profits

    @abstractmethod
    def adjust(self, *args, **kwargs):
        pass

    @property
    def amount(self):
        """This is just here so I can have a common attribute in everything that will allow me to figure out the
        waterfall later on"""
        if self._amount is not None:
            return self._amount
        return self.earnings_and_profits

    @amount.setter
    def amount(self, value):
        self._amount = value



class CurrentEP(EarningsAndProfits):
    """Current E & P, or CEP"""

    def __init__(self, taxable_income=0):
        """
        Additions:
            Tax exempt income
            Dividends received deduction
            collection of proceeds from life insurance policy on life of corp employee (in excess of surrender value)
            Deferred gain on installment sale (all gain is added to E & P in year of sale)
            Deduction of carryovers (charitable contribution, NOL, capital loss)
            Federal income tax refund
            Excess depletion

        Subtractions:
            Future recognition of installment sale gross profit
            Excess charitable contributions and excess capital loss incurred
            Federal income taxes paid
            Loss on sale between related parties
            Nondeductible fines, penalties, & other expenses
            Payment of premiums on life insurance policy on life of corp employee

        Etc.

        Additions and subtractions must be iterables.  Taxable income can be int or float.
        """
        super().__init__()
        self.clear()
        self._taxable_income = taxable_income

    def add_addition(self, adjustment):
        self._positive += abs(adjustment)

    def add_subtraction(self, adjustment):
        self._negative -= abs(adjustment)

    @property
    def taxable_income(self):
        return self._taxable_income

    @taxable_income.setter
    def taxable_income(self, value):
        self._taxable_income = value

    @property
    def earnings_and_profits(self):
        return self._taxable_income + self._positive + self._negative

    @property
    def adjustment(self):
        return self._adjustment

    def adjust(self, gain):
        self._adjustment = gain
        self.amount = self.earnings_and_profits + gain

    def prorate(self, month, positive_aep=None, distr_amount=None, pro_rata_ratio=None):
        if self.earnings_and_profits < 0:
            prorated = (month / 12) * self.amount
            if prorated + positive_aep.earnings_and_profits < 0:
                raise ValueError("Prorated amount is negative")
        else:
            prorated = distr_amount * pro_rata_ratio
        self.amount = prorated

    def clear(self):
        self._positive = 0
        self._negative = 0
        self._taxable_income = 0
        self._adjustment = 0


class AccumulatedEP(EarningsAndProfits):

    def __init__(self, starting=0):
        super().__init__()
        self._earnings_and_profits = starting

    def adjust(self, current_ep: CurrentEP, distribution_adjustment: (int, float)):
        """
        This is actually step 4 of the distributions checklist, but it's here.
        """
        # Formula:
        # Starting AEP
        # + unadjusted Current E&P
        # + adjustment to CEP for gain (if any)
        # - Distribution adjustment (usu. dividend amount except with loss property (AB) or liability > FMV)

        self._earnings_and_profits += (
                current_ep.earnings_and_profits
                + current_ep.adjustment
                - distribution_adjustment)
        the_adjustment = current_ep.adjustment
        current_ep.clear()
        return the_adjustment



class Corp(object):
    """
    By the way, this is not the corporate object I generally wind up using.  I usually use CorporateShareholder,
    which inherits from this class
    """

    def __init__(self, name=None, aep=None, cep=None):
        self.name = name
        self._aep = aep or AccumulatedEP(0)
        self._cep = cep or CurrentEP(0)

    def record_cep(self, taxable_income, additions, subtractions):
        self._cep.taxable_income = taxable_income
        for addition in additions:
            self._cep.add_addition(addition)

        for subtraction in subtractions:
            self._cep.add_subtraction(subtraction)

    @property
    def cep(self):
        return self._cep

    @property
    def aep(self):
        return self._aep




class CorporateShareholder(NonIndividualShareholder, Corp):
    """If shareholder directly or indirectly owns 50% or more (in value) of the stock in a corporation,
    then stock owned by that corporation is considered proportionately owned by shareholder"""

    def __init__(self, name, owners, total_shares_outstanding, shares=None, aep=None, cep=None, **kwargs):
        super().__init__(name=name, owners=owners, total_shares_outstanding=total_shares_outstanding,
                         shares=shares, aep=aep, cep=cep, **kwargs)


    def get_shares(self, stockholder, **kwargs):
        shares = stockholder.get_shares(self)
        proportion = shares.shares / self.total_shares

        if proportion >= .5:
            partial = PartialShares(stock_object=self.shares, proportion=proportion)
            return partial
        # Otherwise, you have no partial ownership proportion
        return PartialShares(stock_object=self.shares, proportion=0)

    def get_my_shares(self, corp):
        total_shares = Aggregated()
        total_shares.append(self._non_constructive(corp))

        if corp in self.owners:
            shares = corp.get_shares(self)
            proportion = shares.shares / self.total_shares

            if proportion >= .5:
                # then all shares owned by that owner are considered constructively owned
                total_shares.append(corp.get_shares(corp))
        return total_shares


    def total_outstanding_fmv(self):
        tot = 0
        for owner in self.owners:
            if owner.shares.corp == self.name:
                tot += owner.shares.fmv
            else:
                for stock in owner.portfolio:
                    if stock.corp == self.name:
                        tot += stock.fmv
                        break
        return tot

    def ownership(self, shareholder):
        """Gets ownership % of shareholder"""
        shares = shareholder.get_shares(self)
        return shares / self.total_shares

    def ownership_with_additional_shares(self, shareholder, num_additional_shares):
        """Gets what ownership % would be if additional shares"""
        shares = shareholder.get_shares(self)
        return (shares + num_additional_shares) / self.total_shares





############ Control Groups ########################



class ControlledGroup(object):
    """A controlled group is a collection of businesses that are related to one another"""

    def __init__(self, corporations=()):
        self._corps = {}
        # Totals for certain shared items that can be shared within the controlled group
        self._shared_items = {'sect179_max': YearConstants()['Section179_limit'],
                              'gen_business_credit_offset': 250_000,
                              "accumulated_earnings_tax_credit": 250_000}
        self.add_corps(*corporations)

    @property
    def allocation_between_members(self):
        try:
            return self._allocation_between_members
        except AttributeError:
            # Default is that all members of the group are weighted equally
            return {c: 1/len(self._corps) for c in self._corps}

    @allocation_between_members.setter
    def allocation_between_members(self, value):
        """
        Note: to ACTUALLY set this in real life, you also must attach a copy of consent from each
        member to your tax return
        """
        if not isinstance(value, dict):
            raise TypeError("Must be dictionary of member_class: percent allocation")
        # if not copy_of_consent_from_each_member_on_tax_return:
        #     raise TypeError("Must attach a written copy of consent from each member to your tax return!")
        self._allocation_between_members = value


    def get_limit(self, year, corp, limit_name):
        allocation_of_limit = self.allocation_between_members
        limit = self._shared_items[limit_name]
        if limit_name == 'sect179_max':
            return allocation_of_limit[corp] * limit[f"{year}"]
        return allocation_of_limit[corp] * limit

    def add_corps(self, *corporations):
        for corp_entity in corporations:
            try:
                self._corps[corp_entity.name] = corp_entity
            except AttributeError:
                self._corps[corp_entity] = Corp(corp_entity)

    def remove_corps(self, *corporations):
        for corp_entity in corporations:
            try:
                del self._corps[corp_entity.name]
            except AttributeError:
                del self._corps[corp_entity]

    def get_my_shares(self, corp):
        shares_owned = Aggregated()
        for subsidiary in self._corps.values():
            shares_owned.append(subsidiary.get_my_shares(corp))
        return shares_owned

    def __getitem__(self, item):
        """To look up a subunit company"""
        return self._corps[item]

    def __repr__(self):
        return str(self)

    def __str__(self):
        return f"{self._corps}"

    def __iter__(self):
        for corp in self._corps.values():
            yield corp


    def __len__(self):
        return len(self._corps)

    def __contains__(self, item):
        if isinstance(item, str):
            try:
                a = self._corps[item]
                return True
            except KeyError:
                return False
        else:
            return item in self._corps.values()



class ParentSubsidiary(ControlledGroup):

    def __init__(self, parent_corp, subsidiaries=()):
        """
        Parent subsidiary relationships require that one corporation must own 80% of total voting power or
        80% of total value outstanding of stock in the other.

        Just because the relationship exists does not mean that they have to recognize it for tax purposes

        :param parent_corp: the parent corporation.  Should be CorporateShareholder class.
        :param subsidiaries: its subsidiaries.  They should also be CorporateShareholder class.
        """
        self._parent = parent_corp
        super().__init__(subsidiaries)

    @property
    def parent(self):
        return self._parent

    def get_my_shares(self, corp):
        shares_owned = self.parent.get_my_shares(corp)
        for subsidiary in self._corps.values():
            shares_owned.append(subsidiary.get_my_shares(corp))
        return shares_owned

    def add_corps(self, *corporations):
        for corp_entity in corporations:
            # Look for corp entity
            shares_owned = self.get_my_shares(corp_entity)
            percent_parent_ownership = shares_owned.shares / corp_entity.total_shares
            percent_value_ownership = shares_owned.fmv / corp_entity.total_outstanding_fmv()

            # One or the other of the above must be >= 80%
            if percent_value_ownership >= .8 or percent_parent_ownership >= .8:
                self._corps[corp_entity.name] = corp_entity
            else:
                raise TypeError("This is not a parent-subsidiary relationship")




class BrotherSister(ControlledGroup):

    def common_owners(self):
        return self._get_common_owners(self._corps)

    @staticmethod
    def _get_common_owners(corps):
        common_owners = None
        for corp in corps:
            if common_owners is None:
                common_owners = set(corp.owners)
            else:
                common_owners = set(corp.owners).intersection(common_owners)
        return common_owners

    class MinDict(dict):
        def min(self, key, alt_min_value):
            """Gets the min of whatever is at the key now and the alternative minimum value (parameter)"""
            try:
                self[key] = min(self[key], alt_min_value)
            except KeyError:
                self[key] = alt_min_value


    def add_corps(self, *corporations):
        # Btw, rights to acquire stock are treated as the stock would be in these tests

        # Small note:
        # There are only allowed to be a maximum of 5 common owners who pass all these tests, but there can be more
        # owners who do not pass the tests or are not necessary to pass the tests.
        # So this is actually kind of a knapsack problem, which is bad in terms of runtime.
        # In other words, we test all different configurations of the partners and see which is the smallest subset that
        # passes all the required tests.  If that subset is bigger than 5, (or one of those is not an individual, trust,
        # or estate) then the tests all fail.

        # Anyways, I'm going to go ahead and ignore that for now, because that'd be more of a programming problem
        # rather than a tax understanding problem, and at the moment, I'm focused on the latter.
        # TODO: Program in the knapsack problem part of this.

        corporations = list(corporations) + list(self._corps.values())
        # Only individuals, trusts, and estates can be common owners.  So need to filter this.
        common_owners = [x for x in self._get_common_owners(corporations) if not isinstance(x, NonIndividualShareholder)]

        if len(common_owners) > 5:
            raise TypeError("This violates the rules of my simplified, non-knapsack version of this.")
        # TODO: Have to do the below check but in a way that does constructive ownership!
        # elif not common_owners:
        #     raise TypeError("No common owners exist between these corporations")

        # For the 50% test.  Must figure out what the minimum ownership is for each owner
        min_percent_ownership = self.MinDict()
        min_fmv = self.MinDict()

        for corp in corporations:
            # Must meet the 80% threshold in either voting power or value
            # Must also meet the 50% threshold for all corps
            # This is a little confusing to say in words.  I'm hoping to find a way to say it better in code

            # 80% test is by corporation (inner loop).  Must tally up what % of each company is owned by group members
            share_ownership = {}
            for owner in filter(lambda x: x in common_owners, corp.owners):
                share_ownership[owner] = Aggregated(owner.get_my_shares(corp))

            total_shares_owned_by_group_members = Aggregated(share_ownership.values())

            # Now we end the inner loop.  At the end of the inner loop, we run the 80% test.
            if (total_shares_owned_by_group_members.shares / corp.total_shares >= .8 or
                total_shares_owned_by_group_members.fmv / corp.total_outstanding_fmv() >= .8):
                # Then the 80% test has been passed and we must consider the 50% test

                # For the 50% test, we need to see the minimum ownership of each member in all self._corps
                # This is the minimum amount that owner owns in all companies in the sister-brother controlled group
                for owner, shrs in share_ownership.items():
                    min_percent_ownership.min(owner, alt_min_value=shrs.shares / corp.total_shares)
                    min_fmv.min(owner, alt_min_value=shrs.fmv / corp.total_outstanding_fmv())
            else:
                # The test fails.  This corporation is not part of the brother-sister group
                raise TypeError(f"{corp.name} failed the 80% test")

        # The outer loop test is the 50% test.  We must now consider the total min ownership
        min_share_ownership = sum(min_percent_ownership.values())
        min_value_ownership = sum(min_fmv.values())

        if min_share_ownership > .5 or min_value_ownership > .5:
            return super().add_corps(*corporations)
        raise TypeError("Corporations failed the 50% test")




