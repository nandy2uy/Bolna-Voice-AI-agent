from eligibility import assess
from speech import eligibility_result, income_readback, loan_readback


def test_hindi_income_readback():
    assert income_readback(50000, "hi") == "आपकी monthly income पचास हज़ार रुपये है, सही है?"


def test_english_loan_readback():
    assert loan_readback(200000, "en") == "You'd like a loan of two lakh rupees, is that right?"


def test_result_rounds_emi_to_nearest_hundred():
    # EMI 4,449 is spoken as "about four thousand four hundred"
    assert "चार हज़ार चार सौ" in eligibility_result(assess(50000, 200000), "hi")
