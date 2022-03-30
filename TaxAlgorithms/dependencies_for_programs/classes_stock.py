"""
(c) 2022 Shoshi (Sharon) Cooper.  No duplication is permitted for commercial use.  Any significant changes made must be
stated explicitly and the original source code, if used, must be available and credited to Shoshi (Sharon) Cooper.

For stock-related classes
"""
from TaxAlgorithms.dependencies_for_programs.aggregated_list_class import Aggregated


class CorporateItems(object):
    def __init__(self, fmv, ab=None, **kwargs):
        super().__init__(**kwargs)
        self.fmv = fmv
        # Adjusted basis will be calculated once it's given to the shareholder
        self.ab = ab


class Stock(CorporateItems):
    def __init__(self, fmv, shares, ab=None, shareholder=None, par=None, corp=None, **kwargs):
        super().__init__(fmv=fmv, ab=ab, **kwargs)
        self.shareholder = shareholder
        self.par = par
        self.shares = shares
        self.corp = corp

    def sell(self, shareholder, num_shares, amount):
        shareholder.shares = type(self)(amount, num_shares)
        shareholder.shares.ab = amount
        proportion = num_shares / self.shares
        gain = amount - proportion * self.ab
        self.shares -= num_shares
        self.fmv = (amount / num_shares) * self.shares
        self.ab -= proportion * self.ab

        self.gain_on_sale = gain

        # Must update amount if I have it.
        if hasattr(self, '_amount'):
            self._amount = self.ab

    @property
    def amount(self):
        try:
            return self._amount
        except AttributeError:
            return self.ab

    @amount.setter
    def amount(self, value):
        self._amount = value


    def set_holding_period(self, properties_contributed):
        """
        We're looking at the holding period in terms of the % of a single share.  If you only sold 1 share of stock
        and you had a 40% to 60% breakdown, you'd still treat 40% as short term and 60% as long term.
        """
        self.long_term_percent = 0
        self.short_term_percent = 0

        if all([prop.does_holding_period_tack for prop in properties_contributed]):
            # Then set holding period to "long term" or longer than 1 year
            self.long_term_percent = 1
        elif all([not prop.does_holding_period_tack for prop in properties_contributed]):
            self.short_term_percent = 1
        else:
            # When you have a mixed bag of holding periods like this, we must allocate based per share based on FMV
            agg_fmv = sum([prop.fmv for prop in properties_contributed])
            for prop in properties_contributed:
                # (property fmv / aggregate fmv)
                if prop.does_holding_period_tack:
                    self.long_term_percent += (prop.fmv / agg_fmv)
                else:
                    self.short_term_percent += (prop.fmv / agg_fmv)

    def __str__(self):
        return f"<{self.shares} in {self.corp}>"

    def __repr__(self):
        return str(self)


class Boot(CorporateItems):
    def __init__(self, fmv):
        super().__init__(fmv)
        # The adjusted basis of boot received by the shareholder is the FMV on date of transfer
        self.ab = self.fmv
        # holding period of boot received is always a fresh start, so starts at 0
        self.holding_period = 0


class Bonds(Boot):
    """Bonds and corporate debt do not count as stock for section 351"""
    pass



class VotingStock(Stock):
    pass

class NonVotingStock(Stock):
    pass


# Partial shares

class PartialShares(object):

    def __init__(self, stock_object, proportion):
        self.stock_object = stock_object
        self.proportion = proportion

    def __getattr__(self, item):
        if item == 'stock_object' or item == 'proportion':
            return super().__getattribute__(item)
        attribute = getattr(self.stock_object, item)
        if isinstance(attribute, (int, float)):
            return attribute * self.proportion
        return attribute



class MultiplePurchases(Aggregated):
    """Multiple Purchases of the same stock"""
    def __init__(self, iterable=(), corp_name=None):
        super().__init__(iterable)
        self.corp = corp_name




class CommonStock(VotingStock):

    def stock_dividend(self, other_stock_object):
        # Adding stock in a stock dividend or a stock split
        if not isinstance(other_stock_object, type(self)):
            # if it's a different class of stock (So preferred or class B common or something)
            total_fmv = self.fmv + other_stock_object.fmv
            basis_of_self = (self.fmv / total_fmv) * self.ab
            basis_of_other = (other_stock_object.fmv / total_fmv) * self.ab
            self.ab = basis_of_self
            other_stock_object.ab = basis_of_other
            return self, other_stock_object
        # if it's the same class of stock, then the number of shares changes so the basis per share changes, but AB
        # does not change
        self.shares += other_stock_object.shares
        return self


class StockRights(object):
    def __init__(self, class_of_stock, price_guaranteed, num_rights, mv_rights_pr, curr_stock):
        """
        Class of stock -- which class of stock it is.  Should be an actual Python class (in this document or otherwise)
        Price guaranteed -- guaranteed purchase price
        Num_rights -- the number of rights you received
        mv_rights_pr -- market value of rights per right
        curr_stock -- if you already own this class of stock, this is where you pass that info in.
        """
        self.class_of_stock = class_of_stock
        self.price_guaranteed = price_guaranteed
        self.num_rights = num_rights
        self.curr_stock = curr_stock

        self._mv_stock_ps = self.curr_stock.fmv / self.curr_stock.shares
        self._mv_rights_pr = mv_rights_pr

        self.ab = 0

        value_of_rights = self.num_rights * self.market_value_rights_per_right
        # Must allocate from original stock if value of rights >= .15 * value of stock
        if value_of_rights >= .15 * self.curr_stock.fmv:
            self.allocate()


    def allocate(self):
        stock_value = self.market_value_stock_per_share * self.curr_stock.shares
        rights_value = self.market_value_rights_per_right * self.num_rights
        cost_of_stock = self.curr_stock.ab
        self.curr_stock.ab = round((stock_value / (stock_value + rights_value)) * cost_of_stock, 2)
        self.ab = round((rights_value / (stock_value + rights_value)) * cost_of_stock, 2)

    @property
    def market_value_stock_per_share(self):
        return self._mv_stock_ps

    @property
    def market_value_rights_per_right(self):
        return self._mv_rights_pr

    def exercise(self, num_rights):
        # FMV is set to None because it does not matter and is not relevant at the moment
        new_shares = self.class_of_stock(fmv=None, shares=num_rights,
                                         ab=(self.ab * num_rights / self.num_rights) +
                                            num_rights * self.price_guaranteed)
        self.ab = self.ab * (self.num_rights - num_rights) / self.num_rights
        self.num_rights -= num_rights
        return new_shares

    def sell(self, num_rights, price_per_right):
        capital_gain = num_rights * price_per_right - self.ab
        self.num_rights -= num_rights
        return capital_gain


def is_stock_nonqualified_preferred(does_holder_have_right_to_require_issuer_to_redeem_or_buy_stock: bool,
                is_issuer_required_to_redeem_buy_stock: bool, does_issuer_have_right_to_redeem_buy_stock: bool,
                likelihood_of_exercising_that_right_on_issue_date: float,
                does_dividend_rate_on_stock_vary_with_reference_to_interest_rates_commodities_etc):
    if does_holder_have_right_to_require_issuer_to_redeem_or_buy_stock:
        return True
    if is_issuer_required_to_redeem_buy_stock:
        return True
    if does_issuer_have_right_to_redeem_buy_stock:
        if likelihood_of_exercising_that_right_on_issue_date > .5:
            return True
    if does_dividend_rate_on_stock_vary_with_reference_to_interest_rates_commodities_etc:
        return True
    return False




class PrefStock(NonVotingStock):

    def __init__(self, fmv, shares, corp=None, ab=None, par=None, **kwargs):
        super().__init__(fmv=fmv, shares=shares, corp=corp, ab=ab, par=par, **kwargs)
        self._info = kwargs


class PreferredStock(object):
    def __new__(cls, fmv, shares, ab=None, corp=None, par=None, flat_dividend=0, dividend_rate=0,
                dividend_rate_reference_index=None, redeemable_for=(), manditorily_redeemable=False,
                holder_has_right_to_require_redemption=False, right_of_issuer_to_redeem_stock=None,
                requirement_of_issuer_to_redeem_stock=False,
                **kwargs):
        information = {'flat_dividend': flat_dividend,
                       'dividend_rate':dividend_rate,
                       'dividend_rate_reference_index': dividend_rate_reference_index,
                       'redeemable_for': redeemable_for,
                       'manditorily_redeemable': manditorily_redeemable,
                       'right_of_issuer_to_redeem_stock': right_of_issuer_to_redeem_stock,
                       'requirement_of_issuer_to_redeem_stock': requirement_of_issuer_to_redeem_stock,
                       'holder_has_right_to_require_redemption': holder_has_right_to_require_redemption
        }
        information.update(kwargs)

        type_of_stock = QualifiedPreferredStock
        # Check if it's nonqualified preferred stock based on the criteria below:
        counts_as_nonqualified_preferred = [
            dividend_rate_reference_index is not None,
            len(redeemable_for) > 0 or manditorily_redeemable,
            requirement_of_issuer_to_redeem_stock or holder_has_right_to_require_redemption,
            right_of_issuer_to_redeem_stock is not None
        ]
        for is_nonqualified in counts_as_nonqualified_preferred:
            if is_nonqualified:
                type_of_stock = NonQualifiedPreferredStock
                break

        return type_of_stock(fmv=fmv, shares=shares, ab=ab, corp=corp, par=par, **information)



class QualifiedPreferredStock(PrefStock):
    pass

class NonQualifiedPreferredStock(PrefStock, Boot):
    pass




class ClassesStock(object):
    """A corporation's collection of stock classes"""

    class DefStck(object):
        def __init__(self, stnding):
            self.issued = stnding
            self.outstanding = stnding
            self.treasury = []
            self.par = None
            self.value = 0
            self.apic = 0
            self.shares_issued = Aggregated()

    def __init__(self, classes_stock_to_outstanding_shares:dict = None):
        self._information = {}

        if classes_stock_to_outstanding_shares is not None:
            for stck_class, outstanding in classes_stock_to_outstanding_shares.items():
                self.add_stock_class(stck_class, outstanding)

    def add_stock_class(self, stock_class, outstanding_shares, issued=None, treasury=0, par=None):
        """Adds a class of stock"""
        self._information[stock_class] = self.DefStck(outstanding_shares)
        issued = issued if issued is not None else outstanding_shares
        for attr_name, attr_val in [('issued', issued), ('treasury', treasury), ('par', par)]:
            self._information[stock_class][attr_name] = attr_val

    def issue(self, stock_class, shares_issued, issue_price, issue_costs):
        """Issues new stock"""
        stock_info = self[stock_class]
        if stock_info.par is None:
            stock_info['value'] += issue_price - issue_costs
        else:
            stock_info['value'] += shares_issued * stock_info.par
            stock_info['apic'] += (issue_price - (shares_issued * stock_info.par)) - issue_costs

        for attr_name in ['issued', 'outstanding']:
            stock_info[attr_name] += shares_issued

        shares = stock_class(fmv=issue_price, shares=shares_issued)
        stock_info['shares_issued'].append(shares)
        return shares

    def treasury_resale(self, stock_class, num_shares, total_sold_for, costs):
        """Resells treasury stock"""
        # TODO: Do this
        raise NotImplementedError("Didn't do this one yet")

    def buy_back(self, shares):
        """Buys back shares as treasury stock"""
        info = self[type(shares)]
        if info.par is None:
            info.value -= shares.fmv
        else:
            info.value -= shares.shares * info.par
            info.apic -= shares.fmv - shares.shares * info.par

        info.outstanding -= shares.shares
        info.treasury.append(shares)


    def __getitem__(self, stock_class):
        return self._information[stock_class]


    def _add_attr(self, attr_name, start=0):
        """Compiles an attribute across all stock classes"""
        total = start
        for stck_class, information in self._information.items():
            total += information[attr_name]
        return total

    @property
    def outstanding(self):
        return self._add_attr('outstanding')

    @property
    def fmv(self):
        return self._add_attr('value') + self._add_attr('apic')

    @property
    def ab(self):
        shrs = Aggregated(self._add_attr('shares_issued', []))
        return shrs.ab











