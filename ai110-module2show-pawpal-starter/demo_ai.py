"""End-to-end demo of the RAG suggestion pipeline (needs GEMINI_API_KEY).

Runs three pets through: retrieve guidelines -> ask Gemini -> validate -> scheduler.
Prints plain text so the output can be pasted into the README as evidence.

    python demo_ai.py
"""

import logging

from diagrams.pawpal_system import Owner, Pet, Scheduler, Task
from suggester import MODEL, suggest_tasks

logging.basicConfig(level=logging.WARNING, format="LOG %(levelname)s: %(message)s")


def build_cases() -> list[Pet]:
    dog = Pet("Mochi", "dog")
    dog.add_task(Task("Morning walk", 30, "high", "daily", time="07:00"))
    dog.add_task(Task("Feeding", 10, "high", "daily", time="18:00"))

    cat = Pet("Luna", "cat")
    cat.add_task(Task("Litter box cleaning", 5, "medium", "daily", time="09:00"))

    hamster = Pet("Biscuit", "hamster")  # no hamster file: falls back to general guidelines
    hamster.add_task(Task("Feeding", 5, "medium", "daily", time="08:00"))

    return [dog, cat, hamster]


def main() -> None:
    print(f"Model: {MODEL}")
    owner = Owner("Jordan")
    for number, pet in enumerate(build_cases(), start=1):
        owner.add_pet(pet)
        print(f"\n=== Case {number}: {pet.name} ({pet.species}) ===")
        print("Existing tasks:", ", ".join(t.description for t in pet.get_tasks()))

        result = suggest_tasks(pet)

        print(f"Retrieved {len(result.guidelines)} guideline(s); topics:",
              ", ".join(sorted({c.topic for c in result.guidelines})))
        if result.error:
            print("ERROR:", result.error)
        for s in result.suggestions:
            print(f"ACCEPTED: {s.description} | {s.duration_minutes} min, {s.priority}, "
                  f"{s.frequency} at {s.time} | source: {s.source.citation()} | "
                  f"confidence {s.confidence:.0%}")
            print(f"          guideline: {s.source.text}")
            pet.add_task(s.to_task())  # stands in for the owner clicking "Add"
        for reason in result.rejected:
            print("REJECTED:", reason)

    scheduler = Scheduler()
    scheduler.build_schedule(owner, {"available_minutes": 90})
    print("\n=== Schedule built from original + accepted tasks (90 min budget) ===")
    print(scheduler.explain_plan())
    print(scheduler.conflict_warning or "No scheduling conflicts.")


if __name__ == "__main__":
    main()
