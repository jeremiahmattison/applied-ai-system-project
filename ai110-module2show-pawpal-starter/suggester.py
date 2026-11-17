"""RAG step: suggest missing care tasks for a pet, grounded in retrieved guidelines.

Flow: retrieve guideline chunks for the pet's species -> ask Gemini to suggest
tasks using ONLY those guidelines -> validate every suggestion in code before
it can reach the scheduler. Anything malformed, ungrounded, or low-confidence
is rejected and logged instead of being shown or added.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field

from diagrams.pawpal_system import Pet, Task
from retriever import Chunk, get_guidelines_by_topic

logger = logging.getLogger(__name__)

MODEL = os.environ.get("PAWPAL_MODEL", "gemini-3.1-flash-lite")
VALID_PRIORITIES = {"low", "medium", "high"}
VALID_FREQUENCIES = {"once", "daily", "weekly"}
MIN_CONFIDENCE = 0.5
REQUEST_TIMEOUT_MS = 60_000  # fail with a message instead of hanging the UI
MAX_SUGGESTIONS = 5
TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

SYSTEM_PROMPT = (
    "You are a pet care planning assistant. You suggest care tasks for one pet "
    "using ONLY the numbered guidelines provided. Every suggestion must cite the "
    "number of the single guideline that supports it. Do not suggest anything the "
    "guidelines do not support, and do not repeat tasks the pet already has. "
    "Set confidence between 0 and 1 for how well the cited guideline supports the "
    "task. If nothing is supported, return an empty suggestions list. "
    "Reply with JSON only, in exactly this shape: "
    '{"suggestions": [{"description": "string, under 80 characters", '
    '"duration_minutes": integer 1-240, "priority": "low" | "medium" | "high", '
    '"frequency": "once" | "daily" | "weekly", "time": "HH:MM in 24-hour format", '
    '"guideline_number": integer, "reason": "string", "confidence": number 0-1}]}'
)


class ModelBlocked(Exception):
    """The model declined to answer (safety filter or empty response)."""


class ModelTruncated(Exception):
    """The model's answer was cut off before it finished."""


class GeminiClient:
    """Thin wrapper so the rest of the code only needs `complete(system, prompt) -> str`."""

    def complete(self, system: str, prompt: str) -> str:
        if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
            raise RuntimeError("GEMINI_API_KEY is not set")
        from google import genai  # imported lazily so the rest of the app runs without it
        from google.genai import types

        # Keep a reference: a throwaway Client() is garbage-collected (and closed) mid-request.
        self._client = getattr(self, "_client", None) or genai.Client(
            http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS)
        )
        response = self._client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                temperature=0.2,
                max_output_tokens=8192,
            ),
        )
        candidates = response.candidates or []
        reason = ""
        if candidates and candidates[0].finish_reason is not None:
            reason = getattr(candidates[0].finish_reason, "name", str(candidates[0].finish_reason))
        if reason == "MAX_TOKENS":
            raise ModelTruncated(reason)
        text = response.text or ""
        if not text:
            raise ModelBlocked(reason or "empty response")
        return text


@dataclass
class Suggestion:
    description: str
    duration_minutes: int
    priority: str
    frequency: str
    time: str
    reason: str
    confidence: float
    source: Chunk  # the retrieved guideline this suggestion is grounded in

    def to_task(self) -> Task:
        return Task(
            self.description,
            duration_minutes=self.duration_minutes,
            priority=self.priority,
            frequency=self.frequency,
            time=self.time,
        )


@dataclass
class SuggestionResult:
    suggestions: list[Suggestion] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)  # reasons, for logs/UI
    guidelines: list[Chunk] = field(default_factory=list)
    error: str | None = None


def retrieve_for_pet(pet: Pet) -> list[Chunk]:
    """Pick guideline chunks for the pet's species, covering every care topic.

    The pet's existing tasks and preferences only decide which chunks rank first
    within each topic; every topic stays represented so gaps can be spotted.
    """
    query = " ".join([task.description for task in pet.get_tasks()] + pet.preferences)
    return get_guidelines_by_topic(pet.species, query, per_topic=2)


def build_user_prompt(pet: Pet, chunks: list[Chunk]) -> str:
    guideline_lines = [f"{i}. [{c.topic}] {c.text}" for i, c in enumerate(chunks, start=1)]
    task_lines = [
        f"- {t.description} ({t.duration_minutes} min, {t.frequency})" for t in pet.get_tasks()
    ] or ["- (none yet)"]
    return (
        f"Pet: {pet.name} ({pet.species})\n\n"
        f"Existing tasks:\n" + "\n".join(task_lines) + "\n\n"
        f"Guidelines:\n" + "\n".join(guideline_lines) + "\n\n"
        f"Suggest up to {MAX_SUGGESTIONS} tasks this pet is missing or that need adjusting."
    )


def validate_suggestion(raw: object, chunks: list[Chunk], existing: set[str]) -> Suggestion:
    """Turn one raw model dict into a Suggestion, or raise ValueError saying why not."""
    if not isinstance(raw, dict):
        raise ValueError("suggestion is not an object")

    description = raw.get("description")
    if not isinstance(description, str) or not description.strip() or len(description) > 80:
        raise ValueError("description missing or too long")
    description = description.strip()
    if description.lower() in existing:
        raise ValueError(f"duplicates existing task {description!r}")

    duration = raw.get("duration_minutes")
    if isinstance(duration, bool) or not isinstance(duration, int) or not 1 <= duration <= 240:
        raise ValueError(f"invalid duration {duration!r}")

    if raw.get("priority") not in VALID_PRIORITIES:
        raise ValueError(f"invalid priority {raw.get('priority')!r}")
    if raw.get("frequency") not in VALID_FREQUENCIES:
        raise ValueError(f"invalid frequency {raw.get('frequency')!r}")

    time = raw.get("time")
    if not isinstance(time, str) or not TIME_PATTERN.match(time):
        raise ValueError(f"invalid time {time!r}")

    number = raw.get("guideline_number")
    if isinstance(number, bool) or not isinstance(number, int) or not 1 <= number <= len(chunks):
        raise ValueError(f"cites a guideline that was not retrieved: {number!r}")

    confidence = raw.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError("confidence is not a number")
    if not 0 <= confidence <= 1:
        raise ValueError(f"confidence out of range: {confidence!r}")
    if confidence < MIN_CONFIDENCE:
        raise ValueError(f"confidence {confidence:.2f} below {MIN_CONFIDENCE}")

    reason = raw.get("reason")
    reason = reason.strip() if isinstance(reason, str) else ""

    return Suggestion(
        description=description,
        duration_minutes=duration,
        priority=raw["priority"],
        frequency=raw["frequency"],
        time=time,
        reason=reason,
        confidence=float(confidence),
        source=chunks[number - 1],
    )


def suggest_tasks(pet: Pet, client=None) -> SuggestionResult:
    """Retrieve guidelines, ask the model for grounded suggestions, and validate them.

    `client` is anything with `complete(system, prompt) -> str` (tests pass a fake).
    Never raises: failures come back on `result.error` so the UI can show a
    friendly message while the rest of the app keeps working.
    """
    result = SuggestionResult()
    result.guidelines = retrieve_for_pet(pet)
    if not result.guidelines:
        result.error = "No care guidelines were found for this pet, so no suggestions were made."
        logger.warning("No guidelines retrieved for %s (%s)", pet.name, pet.species)
        return result

    try:
        client = client or GeminiClient()
        text = client.complete(SYSTEM_PROMPT, build_user_prompt(pet, result.guidelines))
    except ModelBlocked as exc:
        logger.warning("Model declined suggestion request for %s: %s", pet.name, exc)
        result.error = "The model declined this request. Showing guidelines only."
        return result
    except ModelTruncated:
        logger.warning("Suggestion response was cut off at the token limit")
        result.error = "The AI response was cut off. Please try again."
        return result
    except Exception as exc:  # SDK/network/auth errors: report, don't crash the app
        logger.error("Suggestion request failed: %s", exc)
        result.error = f"Could not get AI suggestions ({type(exc).__name__}). Showing guidelines only."
        return result

    try:
        raw_items = json.loads(text)["suggestions"]
        if not isinstance(raw_items, list):
            raise TypeError("'suggestions' is not a list")
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.error("Could not parse model output (%s): %r", exc, text[:200])
        result.error = "The AI response was not in the expected format. Please try again."
        return result

    existing = {t.description.strip().lower() for t in pet.get_tasks()}
    for raw in raw_items[:MAX_SUGGESTIONS]:
        try:
            suggestion = validate_suggestion(raw, result.guidelines, existing)
        except ValueError as exc:
            logger.info("Rejected suggestion: %s", exc)
            result.rejected.append(str(exc))
            continue
        existing.add(suggestion.description.lower())
        result.suggestions.append(suggestion)

    logger.info(
        "Suggestions for %s: %d accepted, %d rejected",
        pet.name, len(result.suggestions), len(result.rejected),
    )
    return result
