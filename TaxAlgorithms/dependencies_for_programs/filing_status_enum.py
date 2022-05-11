from enum import Enum


class FilingStatus(Enum):
    MFJ = 1  # Married Filing Jointly
    MFS = 2  # Married Filing Separately
    SINGLE = 3  # Single
    HH = 4  # Head of Household
    QW = 5  # Qualifying Widower
