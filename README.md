# Hinglish-aware loan pre-check voice agent (LiveKit)

A loan pre-check voice agent that follows how the caller actually speaks (Hindi, English or Hinglish) without flipping language on every English word, and reads numbers back in the language the caller is using.

Built in 3 days with LiveKit Agents (Python, `livekit-agents` 1.8.x) to learn LiveKit hands-on. The loan logic is a deliberately simple stub; the focus is the voice pipeline and the language handling.

Started from LiveKit's [`agent-starter-python`](https://github.com/livekit-examples/agent-starter-python) template.

## What it does

1. Greets the caller in short Hinglish, says it's an AI assistant, and asks whether to start (consent).
2. Collects name, monthly income, loan amount and purpose, one question at a time.
3. Reads every amount back in the caller's language and waits for a "yes" before moving on ("आपकी monthly income पचास हज़ार रुपये है, सही है?").
4. Runs a stub eligibility check (EMI at most 40% of income) and speaks the result.
5. Hands off to a human advisor on request (stub: no real transfer).

It also handles barge-in, silence ("क्या आप अभी भी line पर हैं?") and unclear speech ("माफ़ कीजिए, दोबारा बोलेंगे?"). If the caller declines at the start, it says goodbye and ends the call.

## How the language handling works

**Principle: switch on clear requests, ask on signals, never guess.**

- **Lock on the first substantial reply.** Short replies ("haan", "yes") only set a provisional language for the next question; the first reply with real content (4+ words, e.g. a name or an amount) locks the mode.
- **Two modes.** English: everything in English, amounts as "fifty thousand rupees". Hindi: natural Hinglish, Hindi words in Devanagari and common English words (loan, income, EMI) in English letters, amounts in Hindi words.
- **Clear request → switch immediately** ("Hindi please", "English mein baat karo").
- **Signal → ask once, in the other language.** Signals are an implied request ("mujhe English kam samajh aati hai") or 3 consecutive full turns in the other language.
- **Unrelated mentions are ignored** ("mera form English mein hai").

**The LLM interprets, code decides.** Code detects each turn's language from the STT transcript: Sarvam's codemix mode writes Hindi words in Devanagari and English words in English letters, so the share of Devanagari words tells the language. Only meaning (is this a request? explicit or implied?) needs the LLM, which reports it through a `request_language` tool. Code then applies the policy and updates both the LLM instructions and the TTS language.

## Design choices

- **Logic in code, not the prompt.** Eligibility is a plain function; collected fields and the language mode live in a state object (`LoanState`, attached as session userdata).
- **Code speaks the numbers.** The LLM extracts amounts as integers through tools; code turns the stored integer into words and speaks the read-back with `session.say()`. The caller hears exactly what was stored, which matters because Hindi numbers are easy to confuse (साठ 60 vs सात 7, पैंतालीस 45 vs पचास 50). Tools that speak return `None`, so the LLM doesn't add words of its own.
- **Code guards.** Nothing is saved before consent; a corrected amount loses its confirmation and is read back again; `check_eligibility` refuses until everything is collected and confirmed.
- **One agent with tools**, chosen as the simplest structure for 3 days (LiveKit's TaskGroup would be the next step, see below).

## Pipeline

| Stage | Choice |
|---|---|
| STT | Sarvam `saaras:v4`, `hi-IN`, codemix mode |
| LLM | Gemma 4 31B via LiveKit Inference |
| TTS | Sarvam `bulbul:v3` (`hi-IN` / `en-IN` by mode) |
| Turn detection | LiveKit turn detector (`inference.TurnDetector`), adaptive interruptions |
| Transport / testing | LiveKit Cloud, Agent Console in the browser |

Everything runs on free tiers (LiveKit Cloud Build plan, Sarvam signup credits).

## Code layout

| File | What it does |
|---|---|
| `src/agent.py` | Entry point: session setup, prompt, tools, language hook, event handlers |
| `src/state.py` | `LoanState`: everything known about one call |
| `src/language.py` | Per-turn language detection and the switching policy (plain Python) |
| `src/speech.py` | Every fixed line the agent speaks word for word, in both languages |
| `src/spoken_numbers.py` | Integers to Hindi/English words, Indian numbering (lakh, crore) |
| `src/eligibility.py` | Stub eligibility rule (EMI formula, 40% of income) |
| `src/latency.py` | Per-stage latency logging to `latency.csv` |
| `scripts/stt_compare.py` | Mini STT comparison on recorded clips |
| `scripts/record_clip.py` | Records test clips from the laptop mic |
| `tests/` | Unit tests for the plain-Python modules (language policy, numbers, eligibility, read-backs) |

## Latency

Per-stage metrics come from LiveKit's per-message metrics (`conversation_item_added`) and are written to `latency.csv`. Target: about 1 to 1.5 s from the end of the caller's speech to the agent's first audio.

Measured on one full test call (laptop, Agent Console, free tiers), medians:

| Stage | Metric | Median |
|---|---|---|
| STT final transcript (Sarvam) | `transcription_delay` | 0.76 s |
| End-of-turn decision | `end_of_turn_delay` | 0.86 s (2.5 s on 2 of 7 turns) |
| LLM first token (Gemma 4 31B) | `llm_node_ttft` | 0.56 s |
| TTS first audio (Sarvam bulbul:v3) | `tts_node_ttfb` | 0.21 s |
| **End to end** | `e2e_latency` | **2.66 s** (range 1.88 to 3.52 s, 5 LLM replies) |

**Where the time goes.** The stages add up to about 1.6 s, but replies took 1.9 to 2.7 s. Every slow turn involved a tool call: the LLM first calls the tool, then makes a second call to write the next question, so two LLM round trips happen before the caller hears anything. The end-of-turn decision also can't happen before the STT's final transcript, so the STT sets the floor, and twice the turn detector waited about 2.5 s because it wasn't sure the caller had finished. I measured and diagnosed this but didn't optimize it in the 3 days (see "With more time").

## STT comparison (small directional sample, not a benchmark)

5 Hinglish clips (one speaker, quiet room, laptop mic) built around confusable Hindi numbers: साठ (60) vs सात (7), पैंतालीस (45) vs पचास (50), डेढ़ लाख, ढाई लाख, plus one English sentence. Each clip was streamed to each provider at real-time speed (`scripts/stt_compare.py`). Latency = time from the end of speech to the last final transcript.

| Clip | What I said | Sarvam saaras:v4 (codemix) | Deepgram Nova-3 (multi) |
|---|---|---|---|
| 1 | Meri monthly income saath hazaar hai. | मेरी monthly income साठ हज़ार है। | मेरी monthly income sixty thousand है. |
| 2 | Mujhe paintalis hazaar ka loan chahiye. | मुझे पैंतालीस हज़ार का loan चाहिए। | मुझे पैंतालीस हज़ार का loan चाहिए. |
| 3 | Loan dedh lakh ka chahiye, aur meri income pachattar hazaar hai. | loan डेढ़ लाख का चाहिए। और मेरी income पचहत्तर हज़ार है। | Loan डेढ़ लाख का चाहिए. और मेरी income पचहत्तर हज़ार है. |
| 4 | Main dhai lakh ka loan lena chahta hoon, ghar renovation ke liye. | मैं ढाई लाख का loan लेना चाहता हूँ घर renovation के लिए। | मैं ढाई लाख का loan लेना चाहता हूं. घर renovation के |
| 5 | My monthly income is forty eight thousand and I need a loan of three lakh rupees. | My monthly income is 48000 and I need a loan of 3 lakh rupees. | My monthly income is forty eight thousand. And I need a loan of three lakh rupees. |

| Provider | Amounts correct | Median latency after speech | Price |
|---|---|---|---|
| Sarvam saaras:v4 (hi-IN, codemix) | 7/7 | 0.91 s | ₹30/hour |
| Deepgram Nova-3 (multi, via LiveKit Inference) | 7/7 | 0.39 s | $0.348/hour |

What I took from it:

- **Both got every confusable number right** on clear audio.
- **The real difference is formatting.** The same kind of amount came back as Hindi words (साठ हज़ार), English words inside a Hindi sentence (sixty thousand), digits (48000) and digits plus a unit (3 lakh). This is why the agent never trusts transcript text for numbers: the LLM converts amounts to integers and code speaks the read-back.
- **Deepgram finalized about half a second sooner**, which matters for end-to-end latency.
- **Deepgram dropped the last word of clip 4 both times I ran it**, while Sarvam got it from the same file. With 5 clips I can't tell whether that's the provider or how my script ends the stream.
- With `multi`, Deepgram wrote Hinglish in the same style as Sarvam's codemix mode (Hindi in Devanagari, English words in English letters), so the agent's script-based language detection would likely work with either.

## What broke and how I fixed it

| Symptom | Cause | Fix |
|---|---|---|
| `lk agent init` printed "Failed to run task post_create / set_agent_name_if_present" after "Your agent has been created!" | The template's post-create script expects a `tmp` folder that isn't created on Windows | None needed: the step only sets the agent name, and the default name already matched |
| Console sessions stayed silent, with nothing logged in PowerShell | The Console page wasn't connected to the running agent in the right project (the init link had a placeholder project) | Use the Console link printed by `lk agent dev` |
| "Assertion failed" popup in `livekit_ffi.dll` (`soxr-sys/src/fft4g_cache.h`, `FFT_LEN == -1`); the agent died mid-session | Intermittent; likely a race in the audio resampler's one-time setup, with assertions on in the Windows build (not confirmed) | Clicking Ignore didn't help; it hasn't recurred since. Fallback: run the agent in WSL |
| Template TTS setting `expressive=True` | Makes the LLM emit Fish Audio delivery tags; another TTS would read them aloud | Removed when switching to Sarvam TTS |

## Known limitations

- When the agent asks "Would you prefer English?", that turn's content is skipped (`StopResponse`), so it re-asks anything unsaved.
- Language detection depends on the STT writing Hindi in Devanagari and English in English letters (codemix mode).
- Switching mid-call changes one TTS language for the whole session, so the switch question in the other language is spoken by the current-language voice.
- After the result, the silence re-prompt keeps asking "are you still there?" instead of ending the call.
- Eligibility and handoff are stubs.

## With more time I'd...

1. **Bring end-to-end latency to about 1.5 s**, using what the measurements showed: have tools speak the next fixed question themselves (removing the second LLM call on tool turns), lower the end-of-turn maximum wait, and test Deepgram as the STT (about 0.5 s faster to finalize in my comparison).
2. **Move the collection flow to LiveKit's `TaskGroup`**, which gives ordered steps and going back for corrections without custom guards.
3. **Set the TTS language per utterance**, so the switch question and mixed lines use the right voice settings.
4. **Grow the STT test into a real evaluation**: more speakers, phone-line audio, a spoken-number parser (including Roman-script Hindi), and error rates.

## My take on Hindi voice AI

On clear Hinglish, modern STTs already get confusable Hindi numbers right; in my test both did, 7 of 7. The harder problem is that the same amount comes back in four different formats, so an agent shouldn't trust transcript text for numbers. It should turn amounts into integers and read them back from code.

## Run it yourself (Windows)

```powershell
winget install --id=astral-sh.uv -e
winget install LiveKit.LiveKitCLI
lk cloud auth
uv sync
```

Create `.env.local` with `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` (from your LiveKit Cloud project) and `SARVAM_API_KEY`. Then:

```powershell
lk agent dev
```

Open the Agent Console link it prints and start a session.

## Tests

Unit tests cover the plain-Python modules (language policy, numbers, eligibility, read-backs) and need no API keys:

```powershell
uv run pytest
```