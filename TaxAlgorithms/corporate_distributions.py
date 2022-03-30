"""
(c) 2022 Shoshi (Sharon) Cooper.  No duplication is permitted for commercial use.  Any significant changes made must be
stated explicitly and the original source code, if used, must be available and credited to Shoshi (Sharon) Cooper.

Corporate distributions.
Not super happy with the way I used the class in this one, but I really like the idea that you build your stack and
then pop off it until the distributed amount is down to 0.  That works really nicely.
I should restructure the code in this one if I choose to use it in the future.
"""
from TaxAlgorithms.dependencies_for_programs.property_classes import *


class Transaction(object):
    """Another transaction"""

    def __init__(self, month, callable_function):
        self.month = month
        self.callable_function = callable_function

    def __call__(self, *args, **kwargs):
        return self.callable_function(*args, **kwargs)



class Container(object):
    def __init__(self):
        self.amount = 0

    @property
    def amount(self):
        return self._amount

    @amount.setter
    def amount(self, value):
        self._amount = value


@functools.total_ordering
class Distribution(object):
    def __init__(self, month, shareholders_to_properties_dictionary):
        self.month = month
        self.shareholders_to_properties = {
            sh: Aggregated(prpty) for sh, prpty in
            shareholders_to_properties_dictionary.items()}

    def __lt__(self, other):
        return self.month < other.month

    def __le__(self, other):
        return self.month <= other.month



class PropDistributionEvenEP(object):
    """
    Checklist for Corporate Distributions of Property (note: the term "property" is broadly defined in the IRC!)
    1) Analyze the tax consequences of the distribution to the corporation distributing the property
        (For cash, this will be 0.  Only comes into play when it's property where FMV > AB)
    2) Adjust Current Earnings and Profits of corporation based on step 1's calculated gain
    3) The heart of the analysis!  Analyze consequences to shareholder.
        Sub-steps:
            i) Determine the amount of the distribution under section 301(b)
            ii) Build your stack!  It starts with Stock_AB.  Now, add E&P items.
                    How much E&P?
                    What types of E&P?
                    Allocations?
                    Figure out what to add to the stack here.
            iii) Pop from your stack in order
                When one part of your stack runs own, pop from the next one.
                The breakdown for what parts of stack go into what containers is as follows:
                    E&P --> Dividends
                    Stock AB --> Return of capital
                    Anything left over after stack is exhausted --> Capital Gain
    4) Calculate Accumulated Earnings and Profits for the corporation for the start of the next year
    """

    def __init__(self, corp, *transactions):
        self.corp = corp
        self._transactions = list(transactions)
        self._transactions.sort()

        # When CEP is negative, we must pro-rate it over the course of the year.  So must find the total distr. amount
        total_distr_amount = 0
        for distribution in self._transactions:
            if isinstance(distribution, Distribution):
                total_distr_amount += sum(x.fmv for x in distribution.shareholders_to_properties.values())

        self.total_distr_amount = total_distr_amount

        # Now follow our steps
        self.recognized_gain = self._corporate_consequences()  # Step 1
        self._adjust_cep()  # Step 2
        self.distribution_adjustment = self._shareholder_consequences()  # Step 3
        cep_gain = self.corp.aep.adjust(self.corp.cep, self.distribution_adjustment)  # Step 4

        # just in case I want to double check this
        self.cep_gain = cep_gain

    @property
    def distributions(self):
        return self._transactions

    def _corporate_consequences(self):
        """
        Step 1: Determine corporate consequences.  This only applies when FMV > AB
        """
        recognized_gain = 0
        for distribution in self.distributions:
            try:
                for shareholder, properties in distribution.shareholders_to_properties.items():
                    for ppty in properties:
                        if isinstance(ppty, Cash):
                            continue
                        # If the liability attached to the asset > fmv of the assset, then the selling price is equal
                        # to the amount of the liability
                        if ppty.liability > ppty.fmv:
                            realized_gainloss = ppty.liability - ppty.ab
                        else:
                            # According to tax code, amount realized is simply FMV
                            realized_gainloss = ppty.fmv
                        # if it's a realized loss, it is not recognized.
                        if realized_gainloss >= 0:
                            recognized_gain += realized_gainloss
            except AttributeError:
                pass
        return recognized_gain

    def _adjust_cep(self):
        """Step 2: Adjust CEP for corporation based on the result from step 1"""
        if self.recognized_gain:
            # TODO: For simplicity's sake, this is just gain.  Actually, it would be net of tax.
            #  So this is actually adjusted by self.recognized_gain - 21% * self.recognized_gain.
            self.corp.cep.adjust(self.recognized_gain)

    def _shareholder_consequences(self):
        """
        Step 3: Determine tax consequences to shareholders.
        This involves the process of building and then popping from the stack, as outlined above.
        """
        # Some state variables to allow me to do the pro-rata parts for the different distributions.
        distribution_adjustment = 0
        last_month = 0
        pro_rata_ratio = self.corp.cep.earnings_and_profits / self.total_distr_amount

        # The main loop where we go through each of the distributions by month in order.
        for distribution in self.distributions:
            # If it's another transaction, like a stock sale or something, run that transaction.
            if not isinstance(distribution, Distribution):
                distribution()
                continue

            # Find out the total amount distributed within this distribution.  Important for pro-rata stuff.
            total_distributed = sum(properties.fmv - properties.liability for
                                    properties in distribution.shareholders_to_properties.values())
            # Keeping this here in case there's more than one shareholder and I have to pro-rate AEP
            aep_amt = 0

            for shareholder, properties in distribution.shareholders_to_properties.items():
                # set up -- create my containers for where I will place the amounts in the end.
                dividend = Container()
                return_on_capital = Container()
                capgain = Container()

                # 1) Determine amount of the distribution under section 301(b)
                # Formula: cash received by shareholder + FMV of non-cash property as of date of distribution
                #  - liabilities shareholder assumed
                amount_of_distribution = properties.fmv - properties.liability
                # Can't be < 0!  So must do lesser of that or 0.
                amount_of_distribution = max(amount_of_distribution, 0)

                # Establish stack.  Currently, only the shares are in here.  Their AB is the amount I will pop.
                stack = [(shareholder.shares, return_on_capital)]

                # 2) How much is E&P?
                cep = self.corp.cep
                aep = self.corp.aep

                if cep.earnings_and_profits >= 0 and aep.earnings_and_profits >= 0:
                    # then it's to the extent of first cep, then aep

                    # BUT if there's more than 1 distribution, must pro-rate CEP
                    if len(self.distributions) > 1:
                        cep.prorate(distribution.month, distr_amount=amount_of_distribution,
                                    pro_rata_ratio=pro_rata_ratio)
                        # prorate CEP based on the total number of shareholders in this distribution and the amount
                        # received

                        # AEP is not usually pro-rated, but when there's more than one shareholder, it is prorated.
                        if not aep_amt:
                            aep_amt = aep.amount
                        # prorating for AEP (if required)
                        aep.amount = aep_amt * (amount_of_distribution / total_distributed)

                    # Add AEP, then CEP to the stack.
                    stack.append((aep, dividend))
                    stack.append((cep, dividend))


                elif cep.earnings_and_profits >= 0 and aep.earnings_and_profits < 0:
                    # If CEP is positive and AEP is negative, then only add CEP to the stack.
                    stack.append((cep, dividend))

                elif cep.earnings_and_profits <= 0 and aep.earnings_and_profits > 0:
                    # If CEP is negative and AEP is positive, then attempt to pro-rate CEP and net with AEP.
                    # If the result is positive, this netting will raise a ValueError, and therefore, this property
                    # will not give the shareholder any dividend at all -- so append nothing to the stack.

                    # See CEP Neg AEP Pos method for more detail
                    try:
                        last_month = self.cep_neg_aep_pos(stack, distribution, last_month, dividend)
                    except ValueError:
                        pass
                    # NOTE: THE NET IS APPENDED TO THE STACK IF THERE IS NO VALUEERROR!

                # If ValueError, then no dividend, so I append nothing to the stack

                # 3) Use stack to "waterfall" down the possibilities and calculate consequences
                try:
                    while amount_of_distribution > 0:
                        inpt, output = stack.pop()
                        if inpt.amount < 0:
                            continue
                        adjustment = min(amount_of_distribution, inpt.amount)
                        output.amount += adjustment
                        amount_of_distribution -= adjustment
                        inpt.amount -= adjustment
                except IndexError:
                    # If stack is empty, the remaining amount is capital gain
                    capgain.amount = amount_of_distribution
                    # print(f"Capital gain amount: {amount_of_distribution}")

                distr = {"dividend": dividend.amount, 'return_on_capital': return_on_capital.amount,
                         'capital_gain': capgain.amount}

                # Note: basis for non-cash property to new owner is FMV of property.  Period.

                # Accumulate the amounts from this distribution inside each shareholder object.
                try:
                    for key, val in distr.items():
                        shareholder.distribution[key] += val
                except AttributeError:
                    shareholder.distribution = distr

                # Adjust the shareholder's Adjusted Basis in stock based on the return_on_capital amount.
                shareholder.shares.ab -= return_on_capital.amount

                # Now, we must get the distribution adjustment required for the next step.
                # MOST OF THE TIME, it will be the dividend amount (that's the "else" statement)
                # For a small number of issues, it will be something else.
                ratio = (dividend.amount / (properties.fmv - properties.liability))

                if properties.ab > properties.fmv:
                    distribution_adjustment += properties.ab * ratio
                elif properties.liability > properties.fmv:
                    distribution_adjustment -= (properties.liability - properties.fmv) * ratio
                else:
                    distribution_adjustment += dividend.amount

        return distribution_adjustment


    def cep_neg_aep_pos(self, stack, distribution, last_month, dividend):
        """
        This method handles the case in which CEP is negative and AEP is positive.  It's here because there's a special
        case when it's uneven E&P, so I wanted to be able to override this part in another class.
        """
        cep = self.corp.cep
        aep = self.corp.aep
        # net the two numbers.  If positive, then dividend.  Otherwise, not dividend
        cep.prorate(distribution.month - last_month, aep)
        last_month = distribution.month
        # You prorate cep.  Then you net that with AEP.  The remainder will go into AEP.
        aep.amount += cep.amount
        stack.append((aep, dividend))
        return last_month

