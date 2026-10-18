"""Per-stage latency logging.

LiveKit attaches timing metrics to each message in the conversation. This module
prints them and appends one row per message to latency.csv, which the README's
latency table is built from.

User messages carry: transcription_delay, end_of_turn_delay, on_user_turn_completed_delay.
Agent messages carry: llm_node_ttft, tts_node_ttfb, e2e_latency (end of user speech to
first agent audio; the target is about 1 to 1.5 seconds).
Lines spoken with session.say() skip the LLM, so they have no llm_node_ttft.
"""

import csv
import logging
import time
from pathlib import Path

logger = logging.getLogger("agent")

CSV_PATH = Path("latency.csv")
METRIC_FIELDS = [
    "transcription_delay",
    "end_of_turn_delay",
    "on_user_turn_completed_delay",
    "llm_node_ttft",
    "tts_node_ttfb",
    "e2e_latency",
]
CSV_FIELDS = ["time", "room", "role", *METRIC_FIELDS, "text"]


def record(message, room: str) -> None:
    """Log one conversation message's metrics and append them to latency.csv."""
    metrics = message.metrics or {}
    row = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "room": room,
        "role": message.role,
        "text": (message.text_content or "")[:60],  # a short snippet, to see which turn a row belongs to
    }
    for name in METRIC_FIELDS:
        value = metrics.get(name)
        row[name] = f"{value:.3f}" if isinstance(value, (int, float)) else ""

    is_new_file = not CSV_PATH.exists()
    # utf-8-sig so Excel shows Devanagari text correctly
    with CSV_PATH.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if is_new_file:
            writer.writeheader()
        writer.writerow(row)

    present = {name: row[name] for name in METRIC_FIELDS if row[name]}
    if present:
        logger.info("latency (%s): %s", message.role, present)