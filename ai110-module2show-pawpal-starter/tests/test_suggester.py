import json
from types import SimpleNamespace

import pytest

from diagrams.pawpal_system import Pet, Task
from suggester import (
    MIN_CONFIDENCE,
    ModelBlocked,
    ModelTruncated,
    retrieve_for_pet,
    suggest_tasks,
    validate_suggestion,
)


def good(**overrides):
    item = {
        "description": "Evening walk",
        "duration_minutes": 30,
        "priority": "high",
        "frequency": "daily",
        "time": "18:00",
        "guideline_number": 1,
        "reason": "Dogs need daily exercise.",
        "confidence": 0.9,
    }
    item.update(overrides)
    return item


class FakeClient:
    """Stands in for GeminiClient so tests need no API key or network."""

    def __init__(self, text="", error=None):
        self.calls = []
        self._text, self._error = text, error

    def complete(self, system, prompt):
        self.calls.append({"system": system, "prompt": prompt})
        if self._error:
            raise self._error
        return self._text


@pytest.fixture
def dog():
    pet = Pet("Mochi", "dog")
    pet.add_task(Task("Morning walk", 30, "high"))
    return pet


@pytest.fixture
def chunks(dog):
    return retrieve_for_pet(dog)


def reply(*items):
    return json.dumps({"suggestions": list(items)})


# --- validate_suggestion: each guardrail ---------------------------------

def test_valid_suggestion_is_grounded_in_cited_chunk(chunks):
    s = validate_suggestion(good(guideline_number=2), chunks, set())
    assert s.source == chunks[1]
    assert s.to_task().description == "Evening walk"


@pytest.mark.parametrize(
    "bad",
    [
        {"description": ""},
        {"description": "x" * 81},
        {"duration_minutes": 0},
        {"duration_minutes": 999},
        {"duration_minutes": "30"},
        {"duration_minutes": True},
        {"priority": "urgent"},
        {"frequency": "hourly"},
        {"time": "25:00"},
        {"time": "6pm"},
        {"guideline_number": 0},
        {"guideline_number": 99},
        {"confidence": 1.5},
        {"confidence": "high"},
        {"confidence": MIN_CONFIDENCE - 0.1},
    ],
)
def test_invalid_fields_are_rejected(chunks, bad):
    with pytest.raises(ValueError):
        validate_suggestion(good(**bad), chunks, set())


def test_non_dict_and_missing_fields_rejected(chunks):
    with pytest.raises(ValueError):
        validate_suggestion("walk the dog", chunks, set())
    with pytest.raises(ValueError):
        validate_suggestion({"description": "Walk"}, chunks, set())


def test_duplicate_of_existing_task_rejected(chunks):
    with pytest.raises(ValueError):
        validate_suggestion(good(description="morning walk"), chunks, {"morning walk"})


# --- suggest_tasks: end to end with a fake client ------------------------

def test_happy_path_returns_validated_suggestions(dog):
    client = FakeClient(reply(good(), good(description="Brush teeth", guideline_number=2)))
    result = suggest_tasks(dog, client=client)
    assert result.error is None
    assert [s.description for s in result.suggestions] == ["Evening walk", "Brush teeth"]
    assert result.rejected == []


def test_prompt_contains_retrieved_guidelines_and_pet_tasks(dog):
    client = FakeClient(reply())
    suggest_tasks(dog, client=client)
    prompt = client.calls[0]["prompt"]
    assert "Mochi (dog)" in prompt
    assert "Morning walk" in prompt
    assert "Guidelines:" in prompt and "1. [" in prompt


def test_bad_suggestions_are_dropped_good_ones_kept(dog):
    client = FakeClient(reply(good(), good(priority="urgent"), good(guideline_number=99)))
    result = suggest_tasks(dog, client=client)
    assert len(result.suggestions) == 1
    assert len(result.rejected) == 2


def test_duplicates_within_one_response_are_dropped(dog):
    result = suggest_tasks(dog, client=FakeClient(reply(good(), good())))
    assert len(result.suggestions) == 1


def test_suggestion_matching_existing_task_is_dropped(dog):
    result = suggest_tasks(dog, client=FakeClient(reply(good(description="Morning walk"))))
    assert result.suggestions == []
    assert len(result.rejected) == 1


def test_invalid_json_sets_error_not_crash(dog):
    result = suggest_tasks(dog, client=FakeClient("not json"))
    assert result.suggestions == []
    assert result.error


def test_wrong_json_shape_sets_error(dog):
    result = suggest_tasks(dog, client=FakeClient(json.dumps({"oops": []})))
    assert result.error


def test_api_failure_sets_error_and_keeps_guidelines(dog):
    result = suggest_tasks(dog, client=FakeClient(error=RuntimeError("network down")))
    assert result.suggestions == []
    assert "Could not get AI suggestions" in result.error
    assert result.guidelines  # retrieval still worked


def test_blocked_and_truncated_replies_are_reported(dog):
    assert "declined" in suggest_tasks(dog, client=FakeClient(error=ModelBlocked("SAFETY"))).error
    assert "cut off" in suggest_tasks(dog, client=FakeClient(error=ModelTruncated("MAX_TOKENS"))).error


def test_empty_suggestion_list_is_ok(dog):
    result = suggest_tasks(dog, client=FakeClient(reply()))
    assert result.error is None and result.suggestions == []


def test_accepted_suggestion_flows_into_pet_and_scheduler(dog):
    result = suggest_tasks(dog, client=FakeClient(reply(good())))
    dog.add_task(result.suggestions[0].to_task())
    assert [t.description for t in dog.get_tasks()] == ["Morning walk", "Evening walk"]
    assert dog.get_tasks()[1].pet_name == "Mochi"


def test_no_api_call_when_no_guidelines(monkeypatch, dog):
    monkeypatch.setattr("suggester.retrieve_for_pet", lambda pet: [])
    client = FakeClient(reply(good()))
    result = suggest_tasks(dog, client=client)
    assert client.calls == []
    assert result.error
