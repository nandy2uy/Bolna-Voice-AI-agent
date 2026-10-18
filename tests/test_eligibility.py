from eligibility import MAX_EMI_SHARE_OF_INCOME, assess, estimate_emi


def test_emi_for_two_lakh():
    # 2,00,000 at 12% a year over 60 months
    assert estimate_emi(200000) == 4449


def test_eligible_when_emi_is_within_40_percent():
    result = assess(monthly_income=50000, loan_amount=200000)
    assert result.eligible
    assert result.estimated_emi == 4449


def test_not_eligible_when_emi_is_above_40_percent():
    # the case from a real test call: income 7,000, loan 2,00,000
    assert not assess(monthly_income=7000, loan_amount=200000).eligible


def test_exactly_40_percent_counts_as_eligible():
    emi = estimate_emi(200000)
    income = emi / MAX_EMI_SHARE_OF_INCOME  # EMI is exactly 40% of this income
    assert assess(monthly_income=income, loan_amount=200000).eligible
