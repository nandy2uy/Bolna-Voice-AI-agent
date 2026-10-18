"""Fixed lines the agent speaks word for word, built by code rather than the LLM.

Used wherever exact wording matters: the greeting, number read-backs, the
eligibility result and the handoff. Hindi lines use Devanagari for Hindi words
and English letters for common English words (loan, income, EMI), matching how
Hinglish callers speak.

The Hindi lines use the masculine first person ("करूँगा", "रहा हूँ") to match the
current male TTS voice ("shubh"). Change them if the voice changes.
"""

from eligibility import EligibilityResult
from spoken_numbers import amount_in_words

GREETING = (
    "नमस्ते, मैं एक AI assistant हूँ, और loan pre-check में आपकी मदद करूँगा। "
    "आप Hindi या English, जिसमें भी comfortable हों, उसमें बात कर सकते हैं। "
    "क्या हम शुरू करें?"
)


def income_readback(amount: int, lang: str) -> str:
    words = amount_in_words(amount, lang)
    if lang == "hi":
        return f"आपकी monthly income {words} रुपये है, सही है?"
    return f"Your monthly income is {words} rupees, is that right?"


def loan_readback(amount: int, lang: str) -> str:
    words = amount_in_words(amount, lang)
    if lang == "hi":
        return f"आपको {words} रुपये का loan चाहिए, सही है?"
    return f"You'd like a loan of {words} rupees, is that right?"


def eligibility_result(result: EligibilityResult, lang: str) -> str:
    # Round to the nearest hundred: "about 4,400 rupees" is easier to hear than "4,449".
    emi_words = amount_in_words(round(result.estimated_emi, -2), lang)
    if lang == "hi":
        if result.eligible:
            return (
                f"धन्यवाद। शुरुआती जाँच के हिसाब से, लगभग {emi_words} रुपये की monthly EMI पर "
                "आप इस loan के लिए eligible लगते हैं। ये final approval नहीं है।"
            )
        return (
            f"धन्यवाद। शुरुआती जाँच के हिसाब से, इस loan की EMI लगभग {emi_words} रुपये महीना होगी, "
            "जो आपकी income के चालीस प्रतिशत से ज़्यादा है। इसलिए अभी आप इस amount के लिए eligible नहीं लगते।"
        )
    if result.eligible:
        return (
            f"Thank you. Based on this pre-check, with an estimated EMI of about {emi_words} rupees a month, "
            "you look eligible for this loan. This is not a final approval."
        )
    return (
        f"Thank you. Based on this pre-check, the EMI would be about {emi_words} rupees a month, "
        "which is more than forty percent of your income, so you don't look eligible for this amount right now."
    )


def handoff_line(lang: str) -> str:
    if lang == "hi":
        return "ठीक है, मैं आपको हमारे एक advisor से जोड़ रहा हूँ।"
    return "Sure, I'll connect you to one of our advisors."


def switch_offer(target: str) -> str:
    """Asked once, in the other language, when the caller seems to prefer it."""
    if target == "hi":
        return "क्या आप Hindi में बात करना चाहेंगे?"
    return "Would you prefer to continue in English?"


def still_there(lang: str) -> str:
    """Silence re-prompt, after the caller has been quiet for a while."""
    if lang == "hi":
        return "क्या आप अभी भी line पर हैं?"
    return "Are you still there?"


def please_repeat(lang: str) -> str:
    """When the caller spoke but the STT returned nothing usable."""
    if lang == "hi":
        return "माफ़ कीजिए, दोबारा बोलेंगे?"
    return "Sorry, could you say that again?"


def goodbye(lang: str) -> str:
    """Closing line before the agent ends the call."""
    if lang == "hi":
        return "आपका समय देने के लिए धन्यवाद। नमस्ते!"
    return "Thank you for your time. Goodbye!"