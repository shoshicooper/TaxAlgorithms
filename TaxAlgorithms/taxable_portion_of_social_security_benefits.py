"""
(c) 2022 Shoshi (Sharon) Cooper.  No duplication is permitted for commercial use.  Any significant changes made must be
stated explicitly and the original source code, if used, must be available and credited to Shoshi (Sharon) Cooper.

The algorithm to figure out what part of social security benefits are taxable.

The IRS's worksheet (see Pub. 915) is lengthy, and I've found that textbook explanations for how to compute this are 
often quite confusing. However, I believe the complexity in the IRS' worksheet is caused by optimization.

The simple, elegant, and short algorithm I came up with below is conceptually the same as the IRS's worksheet, 
but without the optimizations and with extra effort given to conceptual clarity.

I've made the conscious decision NOT to optimize this loop at all.  I felt the process had become so optimized on the
IRS's worksheet that it made the process conceptually confusing.  Conceptual confusion can lead to overly complex
code, which can lead to unexpected bugs and difficulty debugging.

That being said, removing the 0% part of the loop would not increase the complexity of the code unduly and should be 
considered if using this for non-conceptual purposes.
"""
from dependencies_for_programs.filing_status_enum import *



# TODO: Replace this with the YearlyConstants() class like it used to be before I moved it to github
# Replace this with whatever these numbers are for the current year, or with an import of a stored file or a request.get
CURRENT_YEAR_THRESHOLDS = {FilingStatus.MFJ: [32_000, 12_000],
                           FilingStatus.MFS: [0, 0],  # Note that this isn't 0 under certain conditions.  See IRC §86
                           FilingStatus.SINGLE: [25_000, 9000],
                           FilingStatus.HH: [25_000, 9000]}
# You will find the numbers you need for these base amounts on the worksheet (currently line items #9 and #11)



def get_taxable_ssa_benefits(filing_status, ssa_benefits, non_ssa_agi, tax_exempt_interest_income,
                             excluded_foreign_income=0, adjustments_for_agi=0, employer_provided_adoption_benefits=0):
    """
    Gets the taxable portion of the social security benefits received during the current tax year.

    :param filing_status: FilingStatus Enum.
    :param ssa_benefits: All social security benefits received as income this tax year
    :param non_ssa_agi: MAGI.  AGI without social security included.
    :param tax_exempt_interest_income: tax exempt interest income
    :param adjustments_for_agi: All adjustments for AGI EXCEPT:
                                - student loan interest
                                - domestic production activities deduction
                                - tuition and fees deduction --> although this is no longer around in 2021
    :param excluded_foreign_income: if taking exclusion for foreign earned income, this would be that exclusion
    :param employer_provided_adoption_benefits: amount of any employer provided adoption benefits
    """
    # Find MAGI w/out SSA Benefits
    magi_less_ssa = sum([
        non_ssa_agi,
        tax_exempt_interest_income,
        excluded_foreign_income,
        employer_provided_adoption_benefits,
        -adjustments_for_agi])

    # Find your base amounts that you will use in your loop
    base_amount0, base_amount1 = CURRENT_YEAR_THRESHOLDS[filing_status]

    # We begin by constructing a stack of (upper_threshold, percent_of_benefits_that_are_taxable) per threshold
    # Note that upper_threshold is called "Base amount" in IRC §86(b).  I call it upper_threshold because it's
    # the upper threshold of each tier we'll be looking at.

    # Place the highest tier first and the lowest tier last, so we can pop off the back of the stack.
    stack = [
        (float("inf"), 0.85),
        (base_amount1, 0.5),
        (base_amount0, 0),
    ]

    # This is where we'll total our taxable portion of social security benefits
    taxable_benefits = 0

    # See IRC §86. Start with magi_less_ssa + 1/2 of ssa_benefits as our initial amount in our 'remaining' caddy.
    # As we pop off the stack, this will 'remaining' caddy will be reduced appropriately until nothing is left.
    remaining = magi_less_ssa + .5 * ssa_benefits

    while remaining:
        upper_threshold, percent = stack.pop()

        # The percent we've just popped will only apply to the amount of our remaining magi that's < upper_threshold
        income_this_applies_to = min(remaining, upper_threshold)
        taxable_benefits += percent * income_this_applies_to

        # However, taxable_benefits will always be limited to percent we popped * ssa benefits
        if percent * ssa_benefits < taxable_benefits:
            taxable_benefits = percent * ssa_benefits

        # Finally, we subtract the top of the current threshold from our "remaining" caddy
        remaining -= income_this_applies_to

    return taxable_benefits

