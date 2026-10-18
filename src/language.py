"""Language policy: which language the caller is speaking, and when to switch.

"The LLM interprets, code decides": this module does the counting and the deciding.
The LLM only reports explicit or implied requests (through the request_language tool).
Plain Python with no LiveKit imports, so it can be tested on its own.

Per-turn detection relies on the STT's codemix mode, which writes Hindi words in
Devanagari and English words in English letters, so the script of each word tells
us its language.
"""

from typing import Literal

from state import Language, LoanState

MIN_WORDS_FOR_SIGNAL = 4  # shorter replies ("haan", "yes", "ok") never lock or count
HINDI_SHARE_FOR_HINDI = 0.3  # Hinglish with a third or more Hindi words counts as Hindi
TURNS_BEFORE_OFFER = 3  # consecutive full turns in the other language before asking once

# Words that carry no language signal on their own, in both scripts.
NEUTRAL_WORDS = {"ok", "okay", "hmm", "hm", "hello", "hi", "ओके", "हम्म", "हेलो", "हैलो"}

PUNCTUATION = ".,!?।\"'-:;()"


def _has_devanagari(word: str) -> bool:
    return any("\u0900" <= ch <= "\u097f" for ch in word)


def _has_latin(word: str) -> bool:
    return any(ch.isascii() and ch.isalpha() for ch in word)


def classify_turn(text: str) -> tuple[Language | None, bool]:
    """Return (language, is_substantial) for one caller turn.

    Language is None when the turn has no language signal (only neutral words or digits).
    """
    words = [w.strip(PUNCTUATION).lower() for w in text.split()]
    words = [w for w in words if w and w not in NEUTRAL_WORDS]
    hindi = sum(1 for w in words if _has_devanagari(w))
    english = sum(1 for w in words if not _has_devanagari(w) and _has_latin(w))
    counted = hindi + english  # digits and symbols like "₹7000" are ignored
    if counted == 0:
        return None, False
    lang: Language = "hi" if hindi / counted >= HINDI_SHARE_FOR_HINDI else "en"
    return lang, counted >= MIN_WORDS_FOR_SIGNAL


def other_language(lang: Language) -> Language:
    return "en" if lang == "hi" else "hi"


def update_after_caller_turn(state: LoanState, text: str) -> bool:
    """Update the language state after a caller turn.

    Returns True if the agent should now ask, once, whether to switch language.
    """
    lang, substantial = classify_turn(text)

    if state.language_mode is None:
        if substantial and lang is not None:
            state.language_mode = lang  # the lock: first substantial reply
        else:
            state.provisional_language = lang or "hi"  # short reply: a hint only; neutral falls back to Hinglish
        return False

    if not substantial or lang is None:
        return False  # short replies neither count toward the streak nor reset it
    if lang == state.language_mode:
        state.other_language_streak = 0
        return False

    state.other_language_streak += 1
    if state.other_language_streak >= TURNS_BEFORE_OFFER and not state.switch_offer_made:
        state.switch_offer_made = True
        return True
    return False


def handle_request(
    state: LoanState, target: Language, explicit: bool
) -> Literal["switched", "offer", "no_change"]:
    """Apply a language request reported by the LLM.

    Clear request -> switch immediately. Implied request -> ask once. Never guess.
    """
    if explicit:
        if state.language_mode == target:
            return "no_change"
        state.language_mode = target
        state.other_language_streak = 0
        return "switched"
    if state.speaking_language == target or state.switch_offer_made:
        return "no_change"
    state.switch_offer_made = True
    return "offer"


def instruction_for(lang: Language) -> str:
    """The language rule given to the LLM for the current mode."""
    if lang == "hi":
        return (
            "Current conversation language: Hindi. Reply in natural Hinglish: Hindi words in "
            "Devanagari script, and common English words like loan, income, EMI and monthly "
            "in English letters."
        )
    return "Current conversation language: English. Reply only in English, even if the caller uses a Hindi word."