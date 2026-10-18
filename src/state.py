"""Call state for the loan pre-check agent.

Plain Python with no LiveKit imports: everything the agent knows about one call.
Tools read and write it through RunContext.userdata.
"""

from dataclasses import dataclass, field
from typing import Literal

Language = Literal["en", "hi"]


@dataclass
class LoanState:
    # Consent: None means "not asked yet"
    consent: bool | None = None

    # Collected fields (numbers are stored as integers, never as words)
    name: str | None = None
    monthly_income: int | None = None
    loan_amount: int | None = None
    loan_purpose: str | None = None

    # Fields the caller confirmed after hearing the read-back
    confirmed: set[str] = field(default_factory=set)

    # Language policy
    language_mode: Language | None = None  # None means not locked yet
    provisional_language: Language = "hi"  # pre-lock hint; Hinglish is the neutral fallback
    other_language_streak: int = 0  # consecutive full turns in the other language
    switch_offer_made: bool = False  # ask about switching only once

    # Human handoff (stub)
    handoff_requested: bool = False

    @property
    def speaking_language(self) -> Language:
        """The language the agent speaks right now: the locked mode, or the pre-lock hint."""
        return self.language_mode or self.provisional_language