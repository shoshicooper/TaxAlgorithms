"""
(c) 2022 Shoshi (Sharon) Cooper.  No duplication is permitted for commercial use.  Any significant changes made must be
stated explicitly and the original source code, if used, must be available and credited to Shoshi (Sharon) Cooper.

The algorithm to net capital gains and losses on a tax return.
This wound up being a wonderfully simple, short, and elegant algorithm.
"""


class BucketToNet(object):
    """A bucket representing a category of capital gains/losses that is taxed at a particular unique rate"""
    __slots__ = ['_amount', 'identifier']

    def __init__(self, identifier, amount=0):
        """
        :param identifier: Identifies what the bucket is.
        :param amount: How much is in the bucket.
        """
        self._amount = amount
        self.identifier = identifier

    def __str__(self):
        return f"<{self._amount} @ {self.identifier}>"

    def __repr__(self):
        return str(self)

    @property
    def amount(self):
        return self._amount

    def is_positive(self):
        """Whether the amount of the bucket is positive.  If it's 0, this MUST return False"""
        return self._amount > 0

    def adjust(self, other):
        """Nets the two if possible, otherwise, does nothing"""
        # Make sure opposite signs
        signs = {self.is_positive(), other.is_positive()}
        if len(signs) == 1:
            return

        netted_amount = sum([self.amount, other.amount])
        # Figure out which is positive
        positive_one = self if self.is_positive() else other
        negative_one = other if self.is_positive() else self

        # If the result is positive, then the leftover is in the positive one's bucket.
        if netted_amount > 0:
            positive_one._amount = netted_amount
            negative_one._amount = 0
            return positive_one
        # Otherwise, the leftover goes in the negative one's bucket
        negative_one._amount = netted_amount
        positive_one._amount = 0
        return negative_one

    def __lt__(self, other):
        try:
            return self.amount < other.amount
        except AttributeError:
            return self.amount < other

    def __iadd__(self, other):
        try:
            self._amount += other.amount
        except AttributeError:
            self._amount += other
        return self




class AllGainSale(object):
    """
    Allows you to allocate capital gains and losses by stcg, ltcg, collectibles, oi, unrecaptured section 1250.

    A useful object when you are dealing with depreciation recapture and other gainloss scenarios where more than
    one category applies to the same transaction.
    """
    __slots__ = ['short_term_capgain', 'long_term_capgain', 'ordinary_income', 'unrecaptured_section_1250',
                 'collectibles']

    def __init__(self, ord_income=0, st_capgain=0, lt_capgain=0, unrecaptured_section_1250=0, collectibles=0):
        self.short_term_capgain = st_capgain
        self.long_term_capgain = lt_capgain
        self.ordinary_income = ord_income
        self.unrecaptured_section_1250 = unrecaptured_section_1250
        self.collectibles = collectibles

    def __str__(self):
        return (f"<oi: {self.ordinary_income}, stcg: {self.short_term_capgain}, ltcg: {self.long_term_capgain}, "
                f"unrecapt_1250: {self.unrecaptured_section_1250}, coll: {self.collectibles}>")

    def __repr__(self):
        return str(self)

    @property
    def total(self):
        return sum([getattr(self, x) for x in self.__slots__])


class NetCapGains(object):
    """The netting process"""
    NET_ORDER = ['short_term_capgain', 'long_term_capgain', 'unrecaptured_section_1250', "collectibles"]

    def __init__(self, *items):
        """Categories should be listed in order of how you want them netted"""
        self._buckets = [BucketToNet(x) for x in self.NET_ORDER]
        # Ordinary income
        self.ordinary = 0

        for item in items:
            self.add_gainloss(item)

    def add_gainloss(self, item: AllGainSale):
        """Adds an item to the correct bucket"""
        self.ordinary += item.ordinary_income
        for bucket in self._buckets:
            bucket += getattr(item, bucket.identifier)


    def _get_net(self):
        """
        Nets everything.

        To get the most beneficial tax outcome, you want to negate the most expensive gain first, then
        the second-most, then the third-most, etc.  Basically, we want the list we go through when comparing
        leftover buckets to be in the exact opposite order from our stack.

        So actually, the algorithm for this is quite simple and elegant:

        ---------------- Algorithm Pseudo-code ---------------------------
            while stack is populated:
                next_category_to_net = stack.pop()

                for netted_category in already_netted_items:
                    if netted_category can be netted against next_category_to_net**
                       net them
                    append next_category_to_net to the end of the already_netted_items


            ** i.e. if they have opposite signs (see are_signs_opposite method for more detail)

        Anything else added into the code simply optimizes the loop by eliminating buckets that have been netted to 0
        """
        # Stack is where I hold my stack where I originally have the bucket items
        # Remaining is where I put them after I've gone through them (backwards order)
        remaining = []
        stack = self._buckets

        while stack:
            next_category_to_net = stack.pop()

            empty = []  # An optimization to get rid of categories that have netted to 0
            for i, netted_category in enumerate(remaining):
                if self.are_opposite_signs(netted_category, next_category_to_net):
                    netted_category.adjust(next_category_to_net)
                # See if netting netted_category and next_category_to_net made bucket empty (netted_category == 0)
                if netted_category == 0:
                    empty.append(i)
            remaining.append(next_category_to_net)

            # Delete empty buckets
            while empty:
                del remaining[empty.pop()]

        return {x.identifier: x.amount for x in remaining if x.amount != 0}

    def net(self):
        """
        Returns the result of netting process as an AllGainSale object, and adds back in ordinary income
        """
        final_result = self._get_net()

        # Make it an AllGainSale object
        final_as_struct = AllGainSale()
        for category_id, amount in final_result.items():
            setattr(final_as_struct, category_id, amount)
        # Add Ordinary Income
        final_as_struct.ordinary_income = self.ordinary

        return final_as_struct

    @staticmethod
    def are_opposite_signs(item1, item2):
        """
        The method is named for the process we are actually doing -- i.e. seeing if item1 and item2 both have the same
        sign or different signs.  By 'sign' I mean if item1 < 0 and item2 < 0.

        However, one should think of this function as a larger concept -- CAN we net item1 and item2?  Is it possible?
        It's impossible to net two positive numbers, because that's not 'netting', that's addition.  Likewise, you
        can't net two negative numbers.  Netting is defined by whether or not the two items have opposite signs.

        So think of this part of the algorithm as being, 'Can we net these?'
        """
        signs = {item1 < 0, item2 < 0}
        return len(signs) > 1

