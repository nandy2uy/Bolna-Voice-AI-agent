import pytest

from spoken_numbers import HINDI_0_TO_99, amount_in_words


def test_hindi_table_covers_0_to_99():
    assert len(HINDI_0_TO_99) == 100


def test_small_numbers():
    assert amount_in_words(0, "hi") == "शून्य"
    assert amount_in_words(0, "en") == "zero"
    assert amount_in_words(45, "hi") == "पैंतालीस"
    assert amount_in_words(45, "en") == "forty five"


def test_confusable_amounts_are_spoken_differently():
    # साठ (60) vs सात (7): the read-back must make a mishearing obvious
    assert amount_in_words(60000, "hi") == "साठ हज़ार"
    assert amount_in_words(7000, "hi") == "सात हज़ार"


def test_indian_numbering_lakh():
    assert amount_in_words(250000, "hi") == "दो लाख पचास हज़ार"
    assert amount_in_words(250000, "en") == "two lakh fifty thousand"


def test_every_unit_together():
    assert amount_in_words(1234567, "hi") == "बारह लाख चौंतीस हज़ार पाँच सौ सड़सठ"
    assert amount_in_words(1234567, "en") == "twelve lakh thirty four thousand five hundred sixty seven"


def test_crore():
    assert amount_in_words(250000000, "hi") == "पच्चीस करोड़"
    assert amount_in_words(250000000, "en") == "twenty five crore"


def test_negative_amount_is_rejected():
    with pytest.raises(ValueError):
        amount_in_words(-1, "en")
