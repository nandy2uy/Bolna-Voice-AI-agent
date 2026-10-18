from language import classify_turn, handle_request, update_after_caller_turn
from state import LoanState


# --- classify_turn: language and whether the turn is substantial (4+ words) ---

def test_short_replies_are_not_substantial():
    assert classify_turn("हाँ") == ("hi", False)
    assert classify_turn("yes") == ("en", False)


def test_neutral_words_carry_no_language():
    assert classify_turn("ok") == (None, False)
    assert classify_turn("hmm okay") == (None, False)


def test_hinglish_counts_as_hindi():
    assert classify_turn("मेरी monthly income पचास हज़ार है") == ("hi", True)


def test_devanagari_name_in_english_sentence_stays_english():
    assert classify_turn("My name is अमृतांश") == ("en", True)


def test_digits_and_symbols_are_ignored():
    assert classify_turn("नहीं, ₹7000।") == ("hi", False)


# --- before the lock ---

def test_short_reply_sets_provisional_language_only():
    state = LoanState()
    update_after_caller_turn(state, "yes")
    assert state.language_mode is None
    assert state.provisional_language == "en"
    assert state.speaking_language == "en"


def test_neutral_reply_falls_back_to_hinglish():
    state = LoanState(provisional_language="en")
    update_after_caller_turn(state, "ok")
    assert state.provisional_language == "hi"


def test_first_substantial_turn_locks_the_language():
    state = LoanState()
    update_after_caller_turn(state, "My name is Amritansh Singh")
    assert state.language_mode == "en"


# --- after the lock: 3-turn signal ---

def english_mode() -> LoanState:
    return LoanState(language_mode="en")


def test_three_full_turns_in_other_language_trigger_one_offer():
    state = english_mode()
    assert update_after_caller_turn(state, "मुझे दो लाख का loan चाहिए") is False
    assert update_after_caller_turn(state, "मेरी monthly income पचास हज़ार है") is False
    assert update_after_caller_turn(state, "घर के renovation के लिए") is True
    assert state.switch_offer_made


def test_offer_is_made_only_once():
    state = english_mode()
    for _ in range(3):
        update_after_caller_turn(state, "घर के renovation के लिए")
    assert update_after_caller_turn(state, "घर के renovation के लिए") is False


def test_short_replies_neither_count_nor_reset_the_streak():
    state = english_mode()
    update_after_caller_turn(state, "मुझे दो लाख का loan चाहिए")
    update_after_caller_turn(state, "हाँ")
    assert state.other_language_streak == 1


def test_same_language_turn_resets_the_streak():
    state = english_mode()
    update_after_caller_turn(state, "मुझे दो लाख का loan चाहिए")
    update_after_caller_turn(state, "I need it for home renovation")
    assert state.other_language_streak == 0


# --- requests reported by the LLM ---

def test_explicit_request_switches_immediately():
    state = english_mode()
    assert handle_request(state, "hi", explicit=True) == "switched"
    assert state.language_mode == "hi"


def test_explicit_request_for_current_language_changes_nothing():
    assert handle_request(english_mode(), "en", explicit=True) == "no_change"


def test_implied_request_asks_once():
    state = english_mode()
    assert handle_request(state, "hi", explicit=False) == "offer"
    assert handle_request(state, "hi", explicit=False) == "no_change"
    assert state.language_mode == "en"  # asking never switches by itself
