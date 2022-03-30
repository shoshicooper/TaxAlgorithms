###### **Tax Algorithms**

I studied for my EA exam by writing algorithms for the tax code 
in Python.  I wanted to think of the tax code in terms of object
oriented programming, rather than thinking of it line by line as 
one might do on the tax forms themselves.

I wrote so much code for this that I obviously won't post it all.
But I'd like to post some of the parts of it that I thought were 
interesting.

I will explain some of the areas of interest below:


**Long Processes into Short Algorithms**

Most of these are for worksheet calculations.  There were a few 
processes that were either long, complicated, or hard to explain
that I managed to find nice, short algorithms for.

These include:

- Determining Partnership Year End
- Netting Capital Gains and Losses
- Computing QBI
- Computing the taxable portion of social security benefits

**IRS Decision Trees**

In the paragraph below, the terms "decision tree" and "dependents" refer
to the IRS definitions of those words, NOT the computer science definitions!

The IRS uses binary trees with simple questions to determine the 
tax consequences of many different things.  Can you claim someone
as a dependent?  Can you file as Head of Household?

They can also be used for more complicated flow-charts, such as 
depreciation, section 179 & bonus depreciation, etc.

I constructed this binary tree structure as a superclass
and later found it abundantly useful for many different parts of the
tax code.  It is also useful for debugging, as you can trace your path 
through the tree and determine which branch contains the bug.

**Other Things**

The rest are just interesting things I programmed that I'll 
throw up as well.  Feel free to look through them!
