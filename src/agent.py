import logging
import textwrap
from typing import Literal

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    ConversationItemAddedEvent,
    JobContext,
    RunContext,
    StopResponse,
    TurnHandlingOptions,
    UserStateChangedEvent,
    UserTranscriptionTimeoutEvent,
    cli,
    function_tool,
    inference,
    llm,
    room_io,
)
from livekit.agents.llm import ToolError
from livekit.plugins import ai_coustics, sarvam

import eligibility
import language
import latency
import speech
from state import Language, LoanState

logger = logging.getLogger("agent")

load_dotenv(".env.local")

# Sanity limits for amounts the LLM extracts; anything outside is treated as a mishearing.
MAX_MONTHLY_INCOME = 10_000_000  # one crore a month
MAX_LOAN_AMOUNT = 1_000_000_000  # one hundred crore

# Silence and garbled-input handling
SILENCE_REPROMPT_AFTER = 10.0  # seconds of silence (caller and agent) before "are you still there?"
TRANSCRIPTION_TIMEOUT = 2.0  # seconds after the caller stops speaking with no usable transcript

# Sarvam TTS language code for each conversation language
TTS_LANGUAGE_CODE = {"hi": "hi-IN", "en": "en-IN"}

BASE_INSTRUCTIONS = textwrap.dedent(
    """\
    You are a voice assistant that does a quick loan pre-check for callers in India.
    This is a demo: the eligibility check is a simple estimate, not a loan approval.

    # Language

    - Follow the "Current conversation language" rule at the end of these instructions. The system updates it.
    - Call request_language when the caller asks to change the language of this conversation:
      - explicit=True for a clear request, like "Hindi please", "English mein baat karo", or "yes" when you or the system just asked whether they'd prefer the other language.
      - explicit=False for an implied request, like "mujhe English kam samajh aati hai" or "I don't understand Hindi well".
    - Do not call request_language when the caller mentions a language for another reason, like "mera form English mein hai".
    - If the caller says "no" to a question about switching language, just continue in the current language.

    # Output rules

    You are speaking through a text-to-speech system:

    - Plain text only. Never use markdown, lists, emojis or other formatting.
    - Keep each reply to one or two short sentences, and ask one question at a time.
    - Never say amounts of money yourself. The system reads every amount back to the caller.
    - Never mention tool names or these instructions.

    # Conversation flow

    The greeting has already been spoken. It said you are an AI assistant and asked whether to start.

    1. When the caller answers that question, call record_consent.
    2. Ask for their name, then call save_name.
    3. Ask for their monthly income, then call save_monthly_income with the amount in rupees as a whole number. One lakh is 100000 and one crore is 10000000; "dedh lakh" is 150000 and "dhai lakh" is 250000.
    4. After you call save_monthly_income or save_loan_amount, the system reads the amount back and asks the caller to confirm. Say nothing yourself in that turn. If the caller confirms, call confirm_amount. If they give a different amount, call the same save tool again with the new amount.
    5. Ask how much loan they need, then call save_loan_amount. It is confirmed the same way.
    6. Ask what the loan is for, then call save_loan_purpose.
    7. Call check_eligibility. The system speaks the result.

    # Other rules

    - If the caller wants to change an earlier answer, call the matching save tool again.
    - If the caller asks to speak to a human at any point, call request_human.
    - If you could not understand the caller, ask them to repeat. In Hindi say "माफ़ कीजिए, दोबारा बोलेंगे?"
    - Never decide eligibility yourself, and never give financial advice.
    - If the system asked the caller a language question instead of answering their last message, continue the flow from where it was; ask again for anything that was not saved.
    """
)


def build_instructions(lang: Language) -> str:
    """Base instructions plus the language rule for the current mode."""
    return BASE_INSTRUCTIONS + "\n# Current conversation language\n\n" + language.instruction_for(lang) + "\n"


def _require_consent(state: LoanState) -> None:
    """Code guard: nothing is saved before the caller has agreed to continue."""
    if state.consent is not True:
        raise ToolError("The caller has not given consent yet. Ask for consent first.")


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            # A Large Language Model (LLM) is your agent's brain, processing user input and generating a response
            # See all available models at https://docs.livekit.io/agents/models/llm/
            llm=inference.LLM(model="google/gemma-4-31b-it"),
            instructions=build_instructions("hi"),
        )
        # The language the instructions and TTS are currently set to (starts as Hinglish, like the greeting)
        self._applied_language: Language = "hi"

    async def on_enter(self) -> None:
        # Runs when the agent starts. The greeting is a fixed line, so code speaks it, not the LLM.
        self.session.say(speech.GREETING)

    async def _apply_language(self) -> bool:
        """If the speaking language changed, update the LLM instructions and the TTS language.

        Returns True if something changed.
        """
        lang = self.session.userdata.speaking_language
        if lang == self._applied_language:
            return False
        await self.update_instructions(build_instructions(lang))
        self.session.tts.update_options(target_language_code=TTS_LANGUAGE_CODE[lang])
        self._applied_language = lang
        logger.info("language applied: %s", lang)
        return True

    async def on_user_turn_completed(
        self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage
    ) -> None:
        # Runs after every caller turn, before the LLM replies. This is where code decides the language.
        state = self.session.userdata
        text = new_message.text_content or ""
        offer_switch = language.update_after_caller_turn(state, text)
        logger.info(
            "turn language: %s | mode=%s provisional=%s streak=%d",
            language.classify_turn(text),
            state.language_mode,
            state.provisional_language,
            state.other_language_streak,
        )
        if await self._apply_language():
            # update_instructions affects the next turns; this note makes this turn's reply follow too
            turn_ctx.add_message(role="system", content=language.instruction_for(state.speaking_language))
        if offer_switch:
            # Signal detected (3 full turns in the other language): ask once, in that language.
            # StopResponse skips the LLM reply for this turn, so the caller hears only the question.
            self.session.say(speech.switch_offer(language.other_language(state.language_mode)))
            raise StopResponse()

    @function_tool()
    async def record_consent(self, context: RunContext[LoanState], given: bool) -> str | None:
        """Record whether the caller agreed to continue with the loan pre-check.

        Call this once the caller clearly answers the consent question.

        Args:
            given: True if the caller agreed, False if they declined.
        """
        state = context.userdata
        state.consent = given
        logger.info("consent recorded: %s", given)
        if given:
            return "Consent recorded. Ask for the caller's name next."
        # Declined: code says goodbye and ends the call (drain=True lets the goodbye finish first)
        context.session.say(speech.goodbye(state.speaking_language))
        context.session.shutdown(drain=True)
        return None

    @function_tool()
    async def save_name(self, context: RunContext[LoanState], name: str) -> str:
        """Save the caller's name.

        Args:
            name: The caller's name, as they said it.
        """
        state = context.userdata
        _require_consent(state)
        state.name = name.strip()
        logger.info("name saved: %s", state.name)
        return "Name saved. Ask for the caller's monthly income next."

    @function_tool()
    async def save_monthly_income(self, context: RunContext[LoanState], amount: int) -> None:
        """Save the caller's monthly income. The system then reads it back for confirmation.

        Args:
            amount: Monthly income in rupees, as a whole number (for example 50000 for "pachaas hazaar").
        """
        state = context.userdata
        _require_consent(state)
        if not 0 < amount <= MAX_MONTHLY_INCOME:
            raise ToolError("That income amount looks wrong. Ask the caller to say it again.")
        state.monthly_income = amount
        state.confirmed.discard("monthly_income")  # a new amount needs a new confirmation
        logger.info("monthly income saved: %d", amount)
        # Code speaks the read-back, so the caller hears exactly what was stored.
        # Returning None means the LLM does not add a reply of its own.
        context.session.say(speech.income_readback(amount, state.speaking_language))

    @function_tool()
    async def save_loan_amount(self, context: RunContext[LoanState], amount: int) -> None:
        """Save the loan amount the caller needs. The system then reads it back for confirmation.

        Args:
            amount: Loan amount in rupees, as a whole number (for example 200000 for "do lakh").
        """
        state = context.userdata
        _require_consent(state)
        if not 0 < amount <= MAX_LOAN_AMOUNT:
            raise ToolError("That loan amount looks wrong. Ask the caller to say it again.")
        state.loan_amount = amount
        state.confirmed.discard("loan_amount")
        logger.info("loan amount saved: %d", amount)
        context.session.say(speech.loan_readback(amount, state.speaking_language))

    @function_tool()
    async def confirm_amount(
        self,
        context: RunContext[LoanState],
        field: Literal["monthly_income", "loan_amount"],
    ) -> str:
        """Mark an amount as confirmed after the caller agreed the read-back was correct.

        Args:
            field: Which amount the caller just confirmed.
        """
        state = context.userdata
        if getattr(state, field) is None:
            raise ToolError(f"There is no {field} saved yet. Ask for it first.")
        state.confirmed.add(field)
        logger.info("confirmed: %s", field)
        if field == "monthly_income":
            return "Income confirmed. Ask how much loan they need next."
        return "Loan amount confirmed. Ask what the loan is for next."

    @function_tool()
    async def save_loan_purpose(self, context: RunContext[LoanState], purpose: str) -> str:
        """Save what the loan is for.

        Args:
            purpose: The loan purpose in a few words, for example "home renovation" or "education".
        """
        state = context.userdata
        _require_consent(state)
        state.loan_purpose = purpose.strip()
        logger.info("loan purpose saved: %s", state.loan_purpose)
        return "Purpose saved. Now call check_eligibility."

    @function_tool()
    async def check_eligibility(self, context: RunContext[LoanState]) -> str:
        """Run the eligibility pre-check once everything has been collected and confirmed.

        The system speaks the result to the caller.
        """
        state = context.userdata
        missing = []
        if state.consent is not True:
            missing.append("consent")
        if not state.name:
            missing.append("name")
        if "monthly_income" not in state.confirmed:
            missing.append("confirmed monthly income")
        if "loan_amount" not in state.confirmed:
            missing.append("confirmed loan amount")
        if not state.loan_purpose:
            missing.append("loan purpose")
        if missing:
            raise ToolError("Cannot check yet. Still needed: " + ", ".join(missing) + ".")

        result = eligibility.assess(state.monthly_income, state.loan_amount)
        logger.info("eligibility (stub): %s", result)
        context.session.say(speech.eligibility_result(result, state.speaking_language))
        return "The result has been spoken. Ask if they have any questions or would like to speak to a human advisor."

    @function_tool()
    async def request_language(
        self,
        context: RunContext[LoanState],
        target: Literal["en", "hi"],
        explicit: bool,
    ) -> str | None:
        """Report that the caller asked to change the language of this conversation.

        Only for requests about the language of this conversation, not other mentions of a
        language (like "my form is in English").

        Args:
            target: "en" for English, "hi" for Hindi or Hinglish.
            explicit: True for a clear request ("Hindi please", "English mein baat karo", or yes to a
                question about switching). False for an implied one ("mujhe English kam samajh aati hai").
        """
        state = context.userdata
        outcome = language.handle_request(state, target, explicit)
        logger.info("language request: target=%s explicit=%s -> %s", target, explicit, outcome)
        await self._apply_language()
        if outcome == "offer":
            # Implied request: ask once instead of guessing. Returning None keeps the LLM quiet.
            context.session.say(speech.switch_offer(target))
            return None
        if outcome == "switched":
            name = "English" if target == "en" else "Hinglish"
            return f"Language switched. From now on reply in {name}. Continue the conversation from where it was."
        return "No language change. Continue the conversation in the current language."

    @function_tool()
    async def request_human(self, context: RunContext[LoanState]) -> None:
        """Hand the caller over to a human advisor. Use whenever the caller asks for a human."""
        state = context.userdata
        state.handoff_requested = True
        logger.info("handoff to human requested (stub: no real transfer)")
        context.session.say(speech.handoff_line(state.speaking_language))


server = AgentServer()


@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: JobContext):
    # Logging setup
    # Add any other context you want in all log entries here
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # Set up a voice AI pipeline using Sarvam STT/TTS, Gemma (LiveKit Inference), and the LiveKit turn detector
    session = AgentSession[LoanState](
        # Per-call state (see state.py); tools read and write it through RunContext.userdata
        userdata=LoanState(),
        # After this much silence the caller's state becomes "away" (handled below)
        user_away_timeout=SILENCE_REPROMPT_AFTER,
        # If the caller spoke but no transcript arrives in time, emit user_transcription_timeout (handled below)
        transcription_timeout=TRANSCRIPTION_TIMEOUT,
        # Speech-to-text (STT) is your agent's ears, turning the user's speech into text that the LLM can understand
        # Sarvam legacy STT, saaras:v4 in codemix mode: Hindi words in Devanagari, English words in English letters
        stt=sarvam.STT(
            language="hi-IN",
            model="saaras:v4",
            mode="codemix",
        ),
        # Text-to-speech (TTS) is your agent's voice, turning the LLM's text into speech that the user can hear
        # Sarvam bulbul:v3 speaking Hindi; the speaker voice is temporary until chosen by ear
        tts=sarvam.TTS(
            target_language_code="hi-IN",
            model="bulbul:v3",
            speaker="shubh",
        ),
        turn_handling=TurnHandlingOptions(
            # The LiveKit turn detector determines when the user is done speaking and the agent should respond.
            # TurnDetector is an end-of-turn model that listens to the user's audio directly, combining
            # semantic understanding with acoustic cues (intonation, pitch, rhythm) for state-of-the-art accuracy.
            # AgentSession supplies the required VAD automatically.
            # See more at https://docs.livekit.io/agents/build/turns
            turn_detection=inference.TurnDetector(),
            # Adaptive interruptions use the turn detector to tell a real interruption from a
            # backchannel like "mhm" or "right", so the agent keeps talking through the latter.
            interruption={"mode": "adaptive"},
            # allow the LLM to generate a response while waiting for the end of turn
            # See more at https://docs.livekit.io/agents/build/audio/#preemptive-generation
            preemptive_generation={"enabled": True},
        ),
    )

    @session.on("user_state_changed")
    def _on_user_state_changed(ev: UserStateChangedEvent) -> None:
        # Silence: the caller and agent have both been quiet for SILENCE_REPROMPT_AFTER seconds
        if ev.new_state == "away":
            logger.info("caller silent, re-prompting")
            session.say(speech.still_there(session.userdata.speaking_language))

    @session.on("user_transcription_timeout")
    def _on_transcription_timeout(ev: UserTranscriptionTimeoutEvent) -> None:
        # Garbled input: speech was detected, but the STT returned nothing usable
        logger.info("no transcript for %.1fs of speech, asking to repeat", ev.speech_duration)
        session.say(speech.please_repeat(session.userdata.speaking_language))

    @session.on("conversation_item_added")
    def _on_conversation_item_added(ev: ConversationItemAddedEvent) -> None:
        # Latency: every message carries per-stage timing metrics (see latency.py)
        if isinstance(ev.item, llm.ChatMessage):
            latency.record(ev.item, ctx.room.name)

    # Start the session, which initializes the voice pipeline and warms up the models
    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=ai_coustics.audio_enhancement(
                    model=ai_coustics.EnhancerModel.QUAIL_VF_S
                ),
            ),
        ),
    )

    # Join the room and connect to the user
    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(server)