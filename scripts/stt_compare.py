"""Mini STT comparison: Sarvam (saaras:v4, codemix) vs Deepgram Nova-3 (via LiveKit Inference).

A small directional sample, not a benchmark: a handful of Hinglish clips recorded on a phone.

Setup:
  clips/                 your audio files (m4a, mp3, wav, ogg... anything PyAV can decode)
  clips/reference.csv    one row per clip: file,reference,numbers
                         reference = what you actually said (any script)
                         numbers   = the amounts you said, as digits, separated by ; (e.g. 50000;200000)

Run from the my-agent folder:
  uv run python scripts/stt_compare.py

Each clip is streamed to each provider at real-time speed, the same way the agent streams
a caller's audio. Latency = time from the end of your speech in the clip (found by audio energy,
so silence at the end of a recording doesn't count) to the last final transcript.
Results go to stt_results.csv and stt_results.md.
"""

import asyncio
import csv
import statistics
import sys
import time
from pathlib import Path

import aiohttp
import av
import numpy as np
from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import inference
from livekit.agents import stt as lk_stt
from livekit.plugins import sarvam

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from spoken_numbers import amount_in_words  # noqa: E402  (reused to check numbers written as words)

load_dotenv(".env.local")

CLIPS_DIR = Path("clips")
REFERENCE_CSV = CLIPS_DIR / "reference.csv"
SAMPLE_RATE = 16000
FRAME_MS = 20
SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_MS // 1000
TRAILING_SILENCE_S = 1.0  # silence after each clip, so streaming STTs can finalize
WAIT_FOR_FINAL_S = 6.0  # after the audio ends, how long to wait for final transcripts

# Prices, from each provider's pricing page (October 2026). Update if they change.
SARVAM_INR_PER_HOUR = 30.0  # Sarvam speech to text
DEEPGRAM_USD_PER_MIN = 0.0058  # Deepgram Nova-3 (Multilingual) on LiveKit Inference, Build plan


SARVAM = "Sarvam saaras:v4 (hi-IN, codemix)"
DEEPGRAM = "Deepgram Nova-3 (multi)"
PRICES = {SARVAM: f"₹{SARVAM_INR_PER_HOUR:.0f}/hour", DEEPGRAM: f"${DEEPGRAM_USD_PER_MIN * 60:.3f}/hour"}


def make_providers(http: aiohttp.ClientSession) -> dict[str, lk_stt.STT]:
    return {
        SARVAM: sarvam.STT(language="hi-IN", model="saaras:v4", mode="codemix", http_session=http),
        DEEPGRAM: inference.STT(model="deepgram/nova-3", language="multi", http_session=http),
    }


def load_frames(path: Path) -> tuple[list[rtc.AudioFrame], float]:
    """Decode any audio file to 16 kHz mono 20 ms frames.

    Returns (frames, speech_end): speech_end is when your speech stops in the clip, in seconds,
    found as the last 20 ms frame that is clearly louder than the background.
    """
    resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    pcm = bytearray()
    with av.open(str(path)) as container:
        for frame in container.decode(audio=0):
            for out in resampler.resample(frame):
                pcm += out.to_ndarray().tobytes()
    for out in resampler.resample(None):  # flush
        pcm += out.to_ndarray().tobytes()

    bytes_per_frame = SAMPLES_PER_FRAME * 2
    pcm += bytes(-len(pcm) % bytes_per_frame)  # pad to a whole frame
    samples = np.frombuffer(bytes(pcm), dtype=np.int16).astype(np.float32)
    loudness = np.sqrt((samples.reshape(-1, SAMPLES_PER_FRAME) ** 2).mean(axis=1))  # RMS per frame
    threshold = max(300.0, 0.1 * float(loudness.max()))
    loud_frames = np.nonzero(loudness > threshold)[0]
    speech_end = (loud_frames[-1] + 1) * FRAME_MS / 1000 if len(loud_frames) else len(loudness) * FRAME_MS / 1000

    pcm += bytes(int(TRAILING_SILENCE_S * SAMPLE_RATE) * 2)
    frames = [
        rtc.AudioFrame(
            data=bytes(pcm[i : i + bytes_per_frame]),
            sample_rate=SAMPLE_RATE,
            num_channels=1,
            samples_per_channel=SAMPLES_PER_FRAME,
        )
        for i in range(0, len(pcm), bytes_per_frame)
    ]
    return frames, float(speech_end)


async def transcribe(provider: lk_stt.STT, frames: list[rtc.AudioFrame], speech_end: float) -> tuple[str, float]:
    """Stream frames at real-time speed. Returns (transcript, seconds from end of speech to last final)."""
    stream = provider.stream()
    finals: list[str] = []
    last_final_at = 0.0
    errors: list[str] = []

    async def read_events() -> None:
        nonlocal last_final_at
        try:
            async for ev in stream:
                if ev.type == lk_stt.SpeechEventType.FINAL_TRANSCRIPT and ev.alternatives:
                    text = ev.alternatives[0].text.strip()
                    if text:
                        finals.append(text)
                        last_final_at = time.perf_counter()
        except Exception as e:  # e.g. a provider timing out after the audio ends: keep what arrived
            errors.append(str(e))

    reader = asyncio.create_task(read_events())
    start = time.perf_counter()
    try:
        for i, frame in enumerate(frames):
            stream.push_frame(frame)
            # keep real-time pace: frame i should be sent at start + i * 20 ms
            await asyncio.sleep(max(0.0, start + (i + 1) * FRAME_MS / 1000 - time.perf_counter()))
        stream.end_input()
        try:
            await asyncio.wait_for(asyncio.shield(reader), timeout=WAIT_FOR_FINAL_S)
        except asyncio.TimeoutError:
            pass  # some providers keep the connection open; whatever finals arrived are enough
    finally:
        reader.cancel()
        await stream.aclose()  # also closes the provider's per-stream HTTP session

    if not finals:
        return ("ERROR: " + errors[0]) if errors else "(no transcript)", float("nan")
    return " ".join(finals), max(0.0, last_final_at - (start + speech_end))


NUKTA = "\u093c"  # the dot in ज़/ड़; STTs are inconsistent about it (हज़ार vs हजार)


def _number_forms(n: int) -> list[str]:
    """Ways an amount can appear in a transcript: digits, Hindi words, English words, digits plus a
    unit ("3 lakh"), and the colloquial डेढ़ (1.5x) / ढाई (2.5x) forms, e.g. 150000 = डेढ़ लाख."""
    forms = [str(n), amount_in_words(n, "hi"), amount_in_words(n, "en")]
    units = [
        (10_000_000, ["करोड़", "crore"]),
        (100_000, ["लाख", "lakh"]),
        (1_000, ["हज़ार", "hazaar", "thousand"]),
    ]
    for size, names in units:
        if n * 2 == size * 3:
            forms += [f"डेढ़ {names[0]}", f"dedh {names[1]}"]
        if n * 2 == size * 5:
            forms += [f"ढाई {names[0]}", f"dhai {names[1]}"]
        if (n * 2) % size == 0:  # digits plus a unit, e.g. "3 lakh", "1.5 lakh", "48 हज़ार"
            forms += [f"{n / size:g} {name}" for name in names]
    return forms


def numbers_found(transcript: str, numbers: list[int]) -> tuple[int, int]:
    """How many expected amounts appear in the transcript. Roman-script Hindi is only matched for डेढ़/ढाई."""
    plain = transcript.replace(",", "").replace("₹", "").replace(NUKTA, "").lower()
    hits = sum(
        1 for n in numbers if any(form.replace(NUKTA, "").lower() in plain for form in _number_forms(n))
    )
    return hits, len(numbers)


async def main() -> None:
    with REFERENCE_CSV.open(encoding="utf-8-sig") as f:
        clips = list(csv.DictReader(f))

    rows = []
    total_audio_s = 0.0
    async with aiohttp.ClientSession() as http:
        providers = make_providers(http)
        for clip in clips:
            frames, speech_end = load_frames(CLIPS_DIR / clip["file"])
            total_audio_s += len(frames) * FRAME_MS / 1000
            numbers = [int(n) for n in clip.get("numbers", "").split(";") if n.strip()]
            for name, provider in providers.items():
                print(f"{clip['file']} -> {name} ...", flush=True)
                try:
                    transcript, latency = await transcribe(provider, frames, speech_end)
                except Exception as e:  # keep going if one provider fails on one clip
                    transcript, latency = f"ERROR: {e}", float("nan")
                hits, total = numbers_found(transcript, numbers)
                rows.append(
                    {
                        "clip": clip["file"],
                        "provider": name,
                        "speech_s": f"{speech_end:.1f}",
                        "reference": clip["reference"],
                        "transcript": transcript,
                        "numbers_found": f"{hits}/{total}",
                        "latency_s": f"{latency:.2f}",
                    }
                )
                print(f"   {transcript}\n   numbers {hits}/{total}, latency {latency:.2f}s")
        for provider in providers.values():
            await provider.aclose()

    with open("stt_results.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "| Clip | Provider | What I said | Transcript | Numbers found | Latency (s) |",
        "|---|---|---|---|---|---|",
        *(
            f"| {r['clip']} | {r['provider']} | {r['reference']} | {r['transcript']} | {r['numbers_found']} | {r['latency_s']} |"
            for r in rows
        ),
        "",
        "| Provider | Median latency (s) | Numbers found | Price |",
        "|---|---|---|---|",
    ]
    for name in PRICES:
        mine = [r for r in rows if r["provider"] == name]
        latencies = [float(r["latency_s"]) for r in mine if r["latency_s"] != "nan"]
        hits = sum(int(r["numbers_found"].split("/")[0]) for r in mine)
        total = sum(int(r["numbers_found"].split("/")[1]) for r in mine)
        median = f"{statistics.median(latencies):.2f}" if latencies else "n/a"
        lines.append(f"| {name} | {median} | {hits}/{total} | {PRICES[name]} |")
    lines.append(
        f"\nAudio tested: {total_audio_s / 60:.1f} minutes per provider. "
        "A small directional sample, not a benchmark."
    )
    Path("stt_results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\nWrote stt_results.csv and stt_results.md")


if __name__ == "__main__":
    asyncio.run(main())