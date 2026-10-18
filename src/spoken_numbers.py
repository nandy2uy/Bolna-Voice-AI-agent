"""Turn integer rupee amounts into words the TTS can speak.

Uses the Indian numbering system (thousand, lakh, crore) in both languages.
Plain Python with no LiveKit imports. Named spoken_numbers.py, not numbers.py,
because Python already has a built-in module called "numbers".
"""

# Hindi numbers 0 to 99 are irregular, so they're listed rather than built from parts.
HINDI_0_TO_99 = [
    "शून्य", "एक", "दो", "तीन", "चार", "पाँच", "छह", "सात", "आठ", "नौ",
    "दस", "ग्यारह", "बारह", "तेरह", "चौदह", "पंद्रह", "सोलह", "सत्रह", "अठारह", "उन्नीस",
    "बीस", "इक्कीस", "बाईस", "तेईस", "चौबीस", "पच्चीस", "छब्बीस", "सत्ताईस", "अट्ठाईस", "उनतीस",
    "तीस", "इकतीस", "बत्तीस", "तैंतीस", "चौंतीस", "पैंतीस", "छत्तीस", "सैंतीस", "अड़तीस", "उनतालीस",
    "चालीस", "इकतालीस", "बयालीस", "तैंतालीस", "चवालीस", "पैंतालीस", "छियालीस", "सैंतालीस", "अड़तालीस", "उनचास",
    "पचास", "इक्यावन", "बावन", "तिरपन", "चौवन", "पचपन", "छप्पन", "सत्तावन", "अट्ठावन", "उनसठ",
    "साठ", "इकसठ", "बासठ", "तिरसठ", "चौंसठ", "पैंसठ", "छियासठ", "सड़सठ", "अड़सठ", "उनहत्तर",
    "सत्तर", "इकहत्तर", "बहत्तर", "तिहत्तर", "चौहत्तर", "पचहत्तर", "छिहत्तर", "सतहत्तर", "अठहत्तर", "उन्यासी",
    "अस्सी", "इक्यासी", "बयासी", "तिरासी", "चौरासी", "पचासी", "छियासी", "सत्तासी", "अट्ठासी", "नवासी",
    "नब्बे", "इक्यानवे", "बानवे", "तिरानवे", "चौरानवे", "पचानवे", "छियानवे", "सत्तानवे", "अट्ठानवे", "निन्यानवे",
]

ENGLISH_0_TO_19 = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen",
]
ENGLISH_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

# (size, Hindi word, English word), largest first
INDIAN_UNITS = [
    (10_000_000, "करोड़", "crore"),
    (100_000, "लाख", "lakh"),
    (1_000, "हज़ार", "thousand"),
    (100, "सौ", "hundred"),
]


def _english_below_100(n: int) -> str:
    if n < 20:
        return ENGLISH_0_TO_19[n]
    tens, ones = divmod(n, 10)
    return ENGLISH_TENS[tens] + (f" {ENGLISH_0_TO_19[ones]}" if ones else "")


def _below_100(n: int, lang: str) -> str:
    return HINDI_0_TO_99[n] if lang == "hi" else _english_below_100(n)


def _to_words(n: int, lang: str) -> str:
    if n < 100:
        return _below_100(n, lang)
    parts = []
    for size, hindi_unit, english_unit in INDIAN_UNITS:
        count, n = divmod(n, size)
        if count:
            # The crore count can itself be 100 or more, so it's converted recursively.
            parts.append(f"{_to_words(count, lang)} {hindi_unit if lang == 'hi' else english_unit}")
    if n:
        parts.append(_below_100(n, lang))
    return " ".join(parts)


def amount_in_words(n: int, lang: str) -> str:
    """Words for a non-negative whole number, e.g. 250000 -> 'दो लाख पचास हज़ार' or 'two lakh fifty thousand'."""
    if n < 0:
        raise ValueError("amount must not be negative")
    return _to_words(n, lang)