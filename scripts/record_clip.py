"""Record a test clip from the laptop microphone, for the STT comparison.

Usage (from the my-agent folder):
  uv run python scripts/record_clip.py clip1

Start speaking after the prompt appears, then press Enter to stop.
Saves clips/clip1.wav. Uses sounddevice, which livekit-agents already installs.
"""

import sys
import wave
from pathlib import Path

import sounddevice as sd

SAMPLE_RATE = 48000  # widely supported by laptop mics; stt_compare.py resamples to 16 kHz


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "clip"
    out = Path("clips") / f"{name}.wav"
    out.parent.mkdir(exist_ok=True)

    chunks: list[bytes] = []

    def on_audio(indata, frames, time_info, status) -> None:
        chunks.append(bytes(indata))

    with sd.RawInputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", callback=on_audio):
        input(f"Recording {out} ... speak now, then press Enter to stop. ")

    with wave.open(str(out), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)  # 16-bit
        f.setframerate(SAMPLE_RATE)
        f.writeframes(b"".join(chunks))
    seconds = sum(len(c) for c in chunks) / 2 / SAMPLE_RATE
    print(f"Saved {out} ({seconds:.1f} s)")


if __name__ == "__main__":
    main()