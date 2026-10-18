"""STUB eligibility rule for the demo. Not a real lending policy.

Rule: estimate the EMI for the requested loan at a fixed stub interest rate and
tenure; the caller is eligible if that EMI is at most 40% of monthly income.
Plain Python with no LiveKit imports, so it can be tested on its own.
"""

from dataclasses import dataclass

STUB_ANNUAL_INTEREST_RATE = 0.12  # 12% a year (stub)
STUB_TENURE_MONTHS = 60  # 5 years (stub)
MAX_EMI_SHARE_OF_INCOME = 0.40  # EMI must be at most 40% of income


@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    estimated_emi: int  # rupees per month, rounded


def estimate_emi(loan_amount: int) -> int:
    """Standard EMI formula: P * r * (1 + r)^n / ((1 + r)^n - 1)."""
    r = STUB_ANNUAL_INTEREST_RATE / 12
    n = STUB_TENURE_MONTHS
    growth = (1 + r) ** n
    return round(loan_amount * r * growth / (growth - 1))


def assess(monthly_income: int, loan_amount: int) -> EligibilityResult:
    emi = estimate_emi(loan_amount)
    return EligibilityResult(
        eligible=emi <= MAX_EMI_SHARE_OF_INCOME * monthly_income,
        estimated_emi=emi,
    )