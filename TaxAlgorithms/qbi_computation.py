"""
The QBI Deduction made simple.

I've discovered a way to make the QBI calculation far simpler.  It allows you to figure out much
of the QBI computation inside your head, and only use a calculator at the end.

There are two tricks:
 1) factor 20% out of the equation.
 2) Understand that the wage/prop element always includes either +infinity or -infinity.

As a result, you wind up with no if-statements, no alternate branches, no three-different-scenarios.
Just a very general, very easy way to compute QBI, as shown in the function below.

(Note: I did not do Specified Service Trade or Businesses here because I was working on understanding the
conceptual side of the overall computation and did not want to muddle it.  However, that's actually quite simple to
implement SSTOBs. Create a class for QBIInfo that includes attributes qbi, mti, w2_wages, qbp.  Have the
compute_qbi function take parameters year, agi, and qbi_info.  Then adjust the getters for the qbi_info class
accordingly.)
"""
# TODO: Specified service TOBs.  Also, aggregation of QBI has not yet been done
from TaxAlgorithms.dependencies_for_programs.filing_status_enum import FilingStatus
from TaxAlgorithms.yearly_constants.load_yearly_constants import YearConstants


def compute_qbi(year, filing_status, agi, qbi, mti, w2_wages=0, qbp=0):
    """
    The basic concept:
        For all situations, QBI boils down to finding the min between three different elements:
            1) MTI
            2) QBI
            3) Wage_prop (can be infinite)
        This gives you:
            deduction = min(.2*QBI, .2*MTI, max(2 * .25 wages, .25 wages + .025 qbp))
            ...which is the same thing as...
            deduction = 0.2 * min(QBI, MTI, max(2 * wages, wages + 0.1 * qbp))

        The above formula will be the heart and soul of the QBI calc.  Everything else is just an adjustment to limit
        the QBI in some crucial way.

        For example, if you are not over the phaseout threshold, wage_prop will be adjusted to include infinity.
        That'll make the max infinite, and since we're taking the min directly afterwards, this ensures that wage_prop
        will never be chosen.

        If you are between thresholds, you will be adjusting the qbi part of the equation.

        But you will still always default back to the same basic equation.

    The basic equation:
        qbi_deduction = 20% * min(mti, qbi, 1.25 * max(wage_prop))
    """

    # Step 1: Figure out whether we are placing -infinity or +infinity at the end of our wage_prop element.

    thresh = get_phaseout_info(filing_status, year)
    # factor is what we'll be multiplying float("inf") by.  If agi < max phaseout, there is no limit, so we'll use
    # positive infinity.  If there is a limit, we'll use -infinity.  That way, the mins and maxes work out properly.
    factor = -1 if (agi >= (thresh.lower + thresh.size)) else 1

    # Step 2: Create our three elements.
    # --> Keep in mind that you can figure out, in your head, if you need to use wage_prop.
    #       You are comparing 2 x wages (easy computation) vs. wages + 10% qbp (easy computation) vs. +/- inf.

    wage_prop_items = [
        2 * w2_wages,
        w2_wages + 0.1 * qbp,
        factor * float("inf")
    ]

    elements = {'mti': mti, 'qbi': qbi, 'wage_prop': 1.25 * max(wage_prop_items)}

    # Step 3: Decrease the QBI element by the amount we are in mid-phaseout.  If we're not in mid-phaseout,
    #  this step will decrease the QBI element by 0.

    # Note that the mid phaseout reduction still allows us to factor out the common 20%.
    # We are merely adjust the elements['qbi'] slot by decreasing the value a little.
    # The amount we decrease it by will be
    #   (MTI - thresh.lower) / thresh.size * (QBI - 1.25 * max(2 * wages, wages + .1 * qbp))

    # Also note: if you are a computer, it will be faster to always do this step b/c no branching.
    # However, if you're not a computer, it will be faster to branch this step and only do it if needed.

    wage_prop_items.pop()  # get rid of the infinite -- we no longer need it
    is_needed = thresh.lower < agi < (thresh.lower + thresh.size)  # Zeros out calc if not required
    reduction_percent = is_needed * (mti - thresh.lower) / thresh.size

    # Now adjust the QBI slot
    elements['qbi'] -= reduction_percent * (qbi - 1.25 * max(wage_prop_items))

    # Step 4: Finally, return 20% of the minimum of all these items
    return .2 * min(elements.values())



class PhaseOutInfo(object):
    __slots__ = ['lower', 'is_mfj']

    def __init__(self, lower_lim, is_mfj=None):
        self.lower = lower_lim
        self.is_mfj = is_mfj

    @property
    def size(self):
        return 50_000 * (2 ** bool(self.is_mfj))


def get_phaseout_info(filing_status, year):
    phaseout_limit = YearConstants().QBI_limit[f"{year}"][filing_status.name.lower()][0]
    return PhaseOutInfo(phaseout_limit, filing_status is FilingStatus.MFJ)
