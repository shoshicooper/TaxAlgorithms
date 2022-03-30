"""
(c) 2022 Shoshi (Sharon) Cooper.  No duplication is permitted for commercial use.  Any significant changes made must be
stated explicitly and the original source code, if used, must be available and credited to Shoshi (Sharon) Cooper.

Like-kind exchanges.
Nothing super exciting, but it works and works effectively.
"""
import collections
from TaxAlgorithms.dependencies_for_programs.aggregated_list_class import Aggregated
from TaxAlgorithms.dependencies_for_programs.invoices_bills_liabilities_etc import Liability



class DressedLiability(object):
    """
    Wrapper for a naked liability.

    Basically, this solves the problem of netting the liabilities separately from the rest of the boot.
    Aggregated() will aggregate any attribute of an item in the list for the whole list.

    With naked liabilities, boot_list.fmv would net all the boot fmvs plus the values of any naked liabilities.
    This was done by design because it's useful for calculations of corporate contributions (section 351).

    However, for section 1031 like-kind exchanges, liabilities must be netted separately.
    This is easy enough if I rename a few of the attributes.  Hence, the "dressing".
    """

    def __init__(self, liability):
        self.fmv = 0
        try:
            self.liability = liability.fmv
        except AttributeError:
            self.liability = liability


class LikeKindExchange(object):
    """
    This object contains information about the exchange after it has been run.
    It can be accessed by using the indexing brackets on the taxpayer (or the taxpayer's name).
    Ex: like_kind = LikeKindExchange(Daisy, property1, Max, property2)
        amount_realized = like_kind[Daisy]['amount_realized']
        amount_recognized = like_kind["Daisy R Sound"]['amount_recognized']
    """

    class PropertyBoot(object):
        __slots__ = ['Property', 'Boot']

        def __init__(self, ppty, boot):
            self.Property = ppty
            self.Boot = Aggregated(boot)

        @property
        def fmv(self):
            return self.Property.fmv + self.Boot.fmv

        @property
        def liability(self):
            return self.Property.liability + self.Boot.liability

    ListEntity = collections.namedtuple("ListEntity", ["A", "B"])

    @classmethod
    def _other_entity(cls, entity):
        return "A" if entity == "B" else "B"

    def __init__(self, taxpayer_a, main_prop_given_up_by_a, taxpayer_b, main_prop_given_up_by_b,
                 assets_given_up_by_a=(), assets_given_up_by_b=()):

        # I must now "dress up" any/all naked liabilities
        given_up = []
        for lst in [assets_given_up_by_a, assets_given_up_by_b]:
            given_up.append([x if not isinstance(x, Liability) else DressedLiability(x) for x in lst])

        self.taxpayers = {'A': taxpayer_a, 'B': taxpayer_b}
        self.assets = {'A': self.PropertyBoot(main_prop_given_up_by_a, Aggregated(given_up[0])),
                       'B': self.PropertyBoot(main_prop_given_up_by_b, Aggregated(given_up[1]))}

        self._info = {'A': {}, 'B': {}}
        self.run_1031()

    def _amount_realized(self, entity):
        """Computes the amount realized for a given entity"""
        other_entity = self._other_entity(entity)

        # Amount received
        constructive_cash = self.assets[entity].Property.liability
        amount_received = self.assets[other_entity].fmv + constructive_cash

        # Adjusted Basis
        constructive_ab = self.assets[other_entity].Property.liability + self.assets[entity].Boot.fmv
        adjusted_basis = self.assets[entity].Property.ab + constructive_ab

        # Selling expenses
        selling_expenses = self.assets[entity].Property.selling_expenses

        # Amount realized
        amount_realized = amount_received - selling_expenses - adjusted_basis
        return amount_realized

    def _net_boot(self, entity):
        """
        Netting Boot

        The rule:
        Boot received can be offset by boot paid.
        Exception: liabilities taken on can only reduce liability relief boot
        """
        other_entity = self._other_entity(entity)

        # Net the liabilities
        liabilities_taken_on = self.assets[other_entity].liability
        liability_relief = self.assets[entity].liability

        net_liability_boot = liability_relief - liabilities_taken_on
        # If it's negative, you have to put this as 0.  If positive, you use it in the next part
        if net_liability_boot < 0:
            net_liability_boot = 0

        # Now net all other boot
        other_boot_paid = self.assets[entity].Boot.fmv
        other_boot_received = self.assets[other_entity].Boot.fmv

        net_other_boot = other_boot_received - other_boot_paid - self.assets[entity].Property.selling_expenses
        return net_liability_boot + net_other_boot

    def _amount_recognized(self, entity, amount_realized):
        """Computes the amount recognized for like-kind exchanges"""
        net_boot = self._net_boot(entity)
        recognized = min(amount_realized, net_boot)

        # Cannot recognize a loss!
        if recognized < 0 and net_boot:
            return 0
        return recognized

    def _new_ab(self, entity, gl_recognized):
        """Computes the adjusted basis in the new property"""
        other_entity = self._other_entity(entity)

        old_ab = self.assets[entity].Property.ab
        money_paid = self.assets[other_entity].Property.liability + self.assets[entity].Boot.fmv
        money_paid += self.assets[entity].Property.selling_expenses
        money_received = self.assets[entity].Property.liability + self.assets[other_entity].Boot.fmv

        new_ab = old_ab + money_paid - money_received + gl_recognized
        return new_ab

    def run_1031(self):
        """Runs the 1031 analysis"""

        for entity in ['A', 'B']:
            # Step 1: Realized gain/loss
            realized = self._amount_realized(entity)
            self._info[entity]['amount_realized'] = realized

            # Step 2: Recognized gain/loss
            #   (I will assume that the client code has checked that this qualifies for like-kind exchange)
            recognized = self._amount_recognized(entity, realized)
            self._info[entity]['amount_recognized'] = recognized

            # Step 2.5 calculate the suspended gain/loss
            suspended_gainloss = realized - recognized

            # Step 3: Calculate new adjusted basis
            new_ab = self._new_ab(entity, recognized)
            self._info[entity]['new_ab'] = new_ab
            new_property = self.assets[self._other_entity(entity)].Property
            new_property.new_ab = new_ab

            # Step 4: Check your work
            #    We check our work by supposing that entity turns around and sells the building immediately
            #    afterwards for FMV in cash assuming no liabilities
            amt_realized = new_property.fmv - new_property.new_ab
            if amt_realized != suspended_gainloss:
                raise ValueError(f"The Double Check failed.  "
                                 f"suspended_gainloss {suspended_gainloss} does not equal amt_realized {amt_realized}")

    def __getitem__(self, taxpayer_name):
        my_entity = None
        for entity in ['A', 'B']:
            tpyr = self.taxpayers[entity]
            if tpyr.name == taxpayer_name or tpyr is taxpayer_name:
                my_entity = entity
                break

        if my_entity is None:
            raise ValueError("Taxpayer is not in the exchange")

        return self._info[my_entity]
