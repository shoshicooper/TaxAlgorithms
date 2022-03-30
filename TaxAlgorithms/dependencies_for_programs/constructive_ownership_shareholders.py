"""
(c) 2022 Shoshi (Sharon) Cooper.  No duplication is permitted for commercial use.  Any significant changes made must be
stated explicitly and the original source code, if used, must be available and credited to Shoshi (Sharon) Cooper.

Constructive Ownership of Stock.
Note: Options to buy stock count as stock for constructive ownership.
"""
from TaxAlgorithms.dependencies_for_programs.classes_stock import *


# Stock Attributions Checklist


class Shareholder(object):

    def __hash__(self):
        return hash(self.name)

    def __init__(self, name, shares=None, **kwargs):
        super().__init__(**kwargs)
        self.name = name
        self._constructive_shares = Aggregated()
        self._portfolio = Aggregated()
        if shares:
            self.shares = shares
            self.shares.shareholder = self
            self._constructive_shares.append(shares)
        else:
            self.shares = None

    @property
    def shares(self):
        return self._shares

    @shares.setter
    def shares(self, stock_object):
        self._shares = stock_object

    @property
    def constructive_shares(self):
        return self._constructive_shares

    def add_constructive_relationship(self, shares_you_are_linking):
        self._constructive_shares.append(shares_you_are_linking)

    def add_another_stock(self, shares):
        shares.shareholder = self
        if self._shares is None:
            self._shares = shares
        else:
            self._portfolio.append(shares)
        self._constructive_shares.append(shares)

    @property
    def portfolio(self):
        return self._portfolio

    def get_shares(self, stockholder_sending_the_fetch_request, corp):
        """A fetch item so that others can fetch shares from me"""
        constructive_shares = Aggregated(
            x for x in self.constructive_shares if x.shareholder.name == stockholder_sending_the_fetch_request.name)
        if constructive_shares:
            return self._non_constructive(corp)
        raise TypeError("Constructive Ownership does not exist")

    def _non_constructive(self, corp):
        all_shares = Aggregated()

        if self.shares.corp == corp or self.shares.corp == corp.name:
            all_shares.append(self.shares)

        all_shares += [x for x in self._portfolio if x.corp == corp or x.corp == corp.name]
        return all_shares

    def get_my_shares(self, corp):
        """Get all shares owned by stockholder constructively"""
        all_shares = self._non_constructive(corp).copy()
        for item in self.constructive_shares:
            if item.shareholder is self:
                continue

            try:
                all_shares.extend(item.shareholder.get_shares(self, corp))
            except TypeError:
                pass
        return all_shares

    def __repr__(self):
        return f"{self.name}"




class ShareholderFamily(Shareholder):
    """Stock held by shareholder's family"""

    def __init__(self, name, shareholder_related_to: Shareholder, shares=None, **kwargs):
        super().__init__(name=name, shares=shares, **kwargs)
        shareholder_related_to.add_constructive_relationship(self.shares)



class ShareholderFamilyReciprocal(ShareholderFamily):
    """The relationship is constructive in two directions"""

    def __init__(self, name, shareholder_related_to: Shareholder, shares=None, **kwargs):
        super().__init__(name=name, shareholder_related_to=shareholder_related_to, shares=shares, **kwargs)
        self.add_constructive_relationship(shareholder_related_to.shares)


class ShareholderFamilyNonReciprocal(ShareholderFamily):
    """One party is constructive with the other, but it only works in a single direction.  Ex. Grandchild."""
    pass


# Reciprocals

class ShareholderSpouse(ShareholderFamilyReciprocal):
    """Spouse of shareholder"""
    pass

class ShareholderChild(ShareholderFamilyReciprocal):
    """Legally adopted children also treated just like any other child.  Same with half-children"""
    pass

class ShareholderParents(ShareholderFamilyReciprocal):
    pass


# Nonreciprocal:

class ShareholderGrandchild(ShareholderFamilyNonReciprocal):
    pass


class TrustEstateShareholder(Shareholder):
    def __init__(self, name, beneficiaries_to_interest_percent, shares=None, **kwargs):
        super().__init__(name=name, shares=shares, **kwargs)
        self.beneficiaries = beneficiaries_to_interest_percent

    def get_my_shares(self, corp):
        shares = super().get_my_shares(corp)
        for beneficiary, interest in self.beneficiaries.items():
            if interest >= .05:
                shares.extend(PartialShares(beneficiary.get_my_shares(), interest))
        return shares



class TrustShareholder(Shareholder):
    def __init__(self, name, beneficiaries=(), shares=None, **kwargs):
        super().__init__(name=name, shares=shares, **kwargs)
        self.beneficiaries = beneficiaries

    def get_my_shares(self, corp):
        shares = super().get_my_shares(corp)
        for beneficiary in self.beneficiaries:
            shares.extend(beneficiary.get_my_shares())

        return shares


class EstateShareholder(Shareholder):
    def __init__(self, name, decedent, shares=None, **kwargs):
        super().__init__(name=name, shares=shares, **kwargs)
        self.decedent = decedent

    def get_my_shares(self, corp):
        shares = super().get_my_shares(corp)
        return shares + self.decedent.get_my_shares(corp)


# Attribution from entities to investors
class NonIndividualShareholder(Shareholder):
    """Shareholders that are not individuals"""

    def __init__(self, name:str, owners:list, total_shares_outstanding:int, shares=None, **kwargs):
        super().__init__(name=name, shares=shares, **kwargs)
        self.owners = owners
        self.total_shares = total_shares_outstanding

    def get_shares(self, stockholder, **kwargs):
        return self.shares



class PartnershipEstateShareholder(NonIndividualShareholder):
    """
    Partnership or Estate.  Also S Corps are considered Partnerships
    Stock owned, directly or indirectly, by a partnership or estate is considered proportionately owned by its
    partners & beneficiaries.

    Reciprocal.  Works in both ways.  Proportionally both ways.
    """

    def get_shares(self, stockholder, **kwargs):
        shares = stockholder.get_shares(self)
        proportion = shares.shares / self.total_shares
        return PartialShares(stock_object=self.shares, proportion=proportion)

    def get_my_shares(self, corp):
        total_shares = Aggregated()
        for owner in self.owners:
            shares = owner.get_shares(self)
            proportion = shares.shares / self.total_shares

            shares = owner.get_my_shares(corp)
            total_shares.append(PartialShares(shares, proportion))
        return total_shares

