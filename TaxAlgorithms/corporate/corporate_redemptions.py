"""
(c) 2022 Shoshi (Sharon) Cooper.  No duplication is permitted for commercial use.  Any significant changes made must be
stated explicitly and the original source code, if used, must be available and credited to Shoshi (Sharon) Cooper.

Corporate redemptions (i.e. buybacks) and whether or not they count as a section 1001 sale/exchange
"""
from TaxAlgorithms.dependencies_for_programs.aggregated_list_class import Aggregated
from TaxAlgorithms.dependencies_for_programs.classes_stock import VotingStock, CommonStock
from TaxAlgorithms.dependencies_for_programs.constructive_ownership_shareholders import ShareholderFamily


class BuyBack(object):

    def __init__(self, month, corp, shareholder, amount_received, *shares_sold_objects, is_family_waiver=False,
                 is_partial_liquidation=False, is_redemption_to_pay_death_taxes=False,
                 value_of_adjusted_gross_estate_decedent=0):
        self.month = month
        self.corp = corp
        self.shareholder = shareholder
        self.shares_sold = Aggregated(shares_sold_objects)
        self.amount_received = amount_received
        self.is_family_waiver = is_family_waiver
        self.is_partial_liquidation = is_partial_liquidation
        self.is_redemption_to_pay_death_taxes = is_redemption_to_pay_death_taxes
        self.value_of_adjusted_gross_estate = value_of_adjusted_gross_estate_decedent

    # Note on gain/loss recognition:

    # Distributions in redemption of stock, qualifying or not, are nonliquidating distributions.
    # Section 311 provides that corporations recognize gain on ALL nonliquidating distributions of appreciated property
    # as if the property had been sold for its FMV. When distributed property is subj. to liability & liability > FMV
    # then liability amount is used to determine the recognized gain.

    # Losses are not recognized on nonliquidating distributions of property.

    def _before_shares_all(self):
        return self.shareholder.get_my_shares(corp=self.corp)

    def _shares_filter(self, shares, class_of_stock_desired):
        return Aggregated(x for x in shares if isinstance(x, class_of_stock_desired))

    @property
    def before_shares_voting_stock(self):
        return self._shares_filter(self._before_shares_all(), VotingStock)

    @property
    def after_shares_voting_stock(self):
        return self.before_shares_voting_stock.shares - self._shares_filter(self.shares_sold, VotingStock).shares

    @property
    def before_shares_common_stock(self):
        return self._shares_filter(self._before_shares_all(), CommonStock)

    @property
    def after_shares_common_stock(self):
        return self.before_shares_common_stock.shares - self._shares_filter(self.shares_sold, CommonStock).shares


    def is_section_1001_exchange(self):
        """
        The method that tells you whether or not this buyback will be treated as a section 1001 exchange or a
        distribution.
        """
        if self._substantially_disproportionate_test():
            return True
        if self._complete_termination_test():
            return True
        if self.is_partial_liquidation:
            return True
        if self._not_essentially_equivalent_to_a_dividend():
            return True
        # This last one usually is tax free b/c estate's tax basis of stock is FMV on date of the decedent's death
        # and the value is unchanged at redemption.
        # HOWEVER, Redemption is limited to the sum of death taxes and funeral and administration expenses
        if self.is_redemption_to_pay_death_taxes and self.shares_sold.fmv > .35 * self.value_of_adjusted_gross_estate:
            #Section 303 applies only to a distribution made with respect to stock of a corporation that is included in
            # the gross estate of a decedent and whose value exceeds 35% of the value of the adjusted gross estate
            return True
        return False



    def _substantially_disproportionate_test(self):
        """The substantially disproportionate test"""
        total_outstanding = self.corp.total_shares

        percent_before = self.before_shares_voting_stock.shares / total_outstanding
        percent_after = self.after_shares_voting_stock / (total_outstanding - self.shares_sold.shares)

        # After the redemption, the shareholder must have less than 50% of combined voting power of all voting classes
        # of stock.
        if percent_after >= .5:
            return False
        # After the redemption, shareholder must have less than 80% of the percentage of voting stock held immediately
        # before redemption
        if percent_after >= .8 * percent_before:
            return False
        # After the redemption, shareholder must have less than 80% of the percentage of common stock held immediately
        # before redemption
        percent_after = self.after_shares_common_stock / (total_outstanding - self.shares_sold.shares)
        percent_before = self.before_shares_common_stock.shares / total_outstanding
        if percent_after >= .8 * percent_before:
            return False

        return True

    def _complete_termination_test(self):
        """The Complete Termination test"""
        # Before shares
        shares_owned = self.shareholder.get_my_shares(self.corp)
        if self.is_family_waiver:
            shares_owned = Aggregated(x for x in shares_owned if not isinstance(x, ShareholderFamily))
        elif isinstance(shares_owned, list):
            shares_owned = Aggregated(shares_owned)

        # After shares must be 0
        return (shares_owned.shares - self.shares_sold.shares) == 0


    def _not_essentially_equivalent_to_a_dividend(self):
        """
        Not essentially equivalent to a dividend test focuses on whether voting percentage change is meaningful
        reduction in control.

        I purposely simplified this test in the code below.  In reality, the rules are a bit wishy-washier than
        I wrote down below.  I decided to focus the code on whether or not the taxpayer would have a strong case
        if they argued a particular way -- based on precedent.

        This is particularly true in terms of the concert issue.  I made the conscious choice to only program in the
        slam-dunk absolutely works case.  However, even if you're not the slam-dunk case, you could still have a strong
        or convincing case.  You'd just have to be very sure you knew what you were doing.

        Really, this should return one of three values: True, False, and Possibly.
        But I didn't do that.

        If True is returned, it means the taxpayer has a strong case for a section 1001 sale/exchange.
        If False, and it's not an area of concert, then the answer is simply False.

        However, if False is returned due to concert issues, the taxpayer should double check how the ownership has
        changed and weigh the non-numerical implications.  Keep in mind that if the taxpayer claims this is a section
        1001 sale/exchange despite this (and all the other tests) returning False, simply due to the concert issue,
        there is a very real chance that the taxpayer and the IRS will not agree.
        """
        num_owners = len(self.corp.owners)
        before = self.before_shares_voting_stock.shares / self.corp.total_shares
        after = self.after_shares_voting_stock / (self.corp.total_shares - self.shares_sold.shares)
        # Focuses on voting percentage -- is it a meaningful reduction in control?
        if num_owners <= 2:
            if before > .5 >= after:
                return True
        # If there are more than 2 owners, there are issues of concert, where one owner can team up with another to
        # get control.  Only matters if you don't have control already, and all parties are unrelated.
        if num_owners > 2:
            if after > .5:
                return False
            if before > .5 > after:
                return True
            if before > .5 and after == .5:
                # If there are more than 2 shareholders, this changes. Maybe they could team up with other shareholders?
                return False
            # Now we get into the concert issue.  What if there's no related shareholders and you could team up?
            if any(isinstance(x, ShareholderFamily) for x in self.corp.owners):
                return False

            could_team_up_before = True
            could_team_up_after = False
            for owner in self.corp.owners:
                if owner is self.shareholder:
                    continue
                # Check if the shareholder could team up with every other person before to get control
                before_redemption = (self.shareholder.shares.shares + owner.shares.shares) / self.corp.total_shares
                if could_team_up_before and before_redemption < .5:
                    could_team_up_before = False

                # Check if the shareholder could team up with every other person after
                # Note: if shareholder could NEVER gain control if they teamed up with ANYONE, then it's a slam-dunk.
                # However, there could be a case for if they couldn't team up with everyone afterwards but could with 1
                # person.  But it's not a slam dunk.
                # I programmed in the slam dunk case.  But there's a LOT of wiggle room here.
                after_redemption = (self.shareholder.shares.shares - self.shares_sold.shares +
                                    owner.shares.shares) / (self.corp.total_shares - self.shares_sold.shares)
                if not could_team_up_after and after_redemption > .5:
                    could_team_up_after = True

            if could_team_up_before and not could_team_up_after:
                return True

        return False

    def adjust_ab_in_stock(self):
        if not self.is_section_1001_exchange():
            self.shareholder.shares.shares -= self.shares_sold.shares
            # Then the AB is not adjusted in aggregate, but the AB/share is split between fewer shares
            return
        # If it is a section 1001 exchange, then the AB per share remains but the aggregate AB is adjusted down
        ab_per_share = self.shareholder.shares.ab / self.shareholder.shares.shares
        self.shareholder.shares.shares -= self.shares_sold.shares
        self.shareholder.shares.ab = ab_per_share * self.shareholder.shares.shares
        return



def min_num_shares_to_qualify_as_substantially_disproportionate(shareholder, corp, shares_reduced=None):
    """
    Finds the minimum number of shares required to buy back to qualify as substantially disproportionate.

    :param shareholder: the shareholder object that you are calculating for
    :param corp: the corp object whose shares you are dealing with
    :param shares_reduced: If the corporation has decided ahead of time how many shares will be reduced, here's where
    that number would go.
    """

    before_shares = shareholder.get_my_shares(corp).shares
    before_percentage = before_shares / corp.total_shares
    # must also be < 50% so keep that in mind.  But I'll start with the 80% one.

    # I will now find out what my limit is.  I have to take .8 * before % and see if the after % is less than it.
    limit_percent = .8 * before_percentage

    # If the limit percent is over 50%, then we're suddenly limited by the first rule (that the afterwards % must be
    # less than 50%).  So we will actually wind up having to switch to 50% here in that case.
    if limit_percent > .5:
        limit_percent = .5

    if shares_reduced is None:
        # Must solve this equation to find answer:
        # (before_shares - x) / (total_shares - x) < limit_percent
        # which solves for x as:
        # x > (limit_percent * total_shares - before) / (limit_percent - 1)

        num_shares = (limit_percent * corp.total_shares - before_shares) / (limit_percent - 1)
        return int(num_shares) + 1

    # If there's a definite number of shares we're reducing by, then factor that into equation
    num_shares = -limit_percent * (corp.total_shares - shares_reduced) + before_shares
    return int(num_shares) + 1

