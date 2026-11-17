# PawPal+ with Guideline-Grounded AI Suggestions

## Original Project

This project extends **PawPal+**, the pet care planner I built in Module 2. The original app let a busy pet owner enter their pets and care tasks (walks, feeding, meds, grooming) and then built a daily plan. It ordered tasks by priority within a time budget, warned about scheduling conflicts, and rescheduled daily and weekly tasks automatically when I marked them done.

## Title and Summary

PawPal+ is a Streamlit app that helps a pet owner plan care across several pets. The scheduler decides what to do and in what order. The new part is a retrieval-augmented (RAG) step that looks up species-specific care guidelines and asks Google's Gemini model to suggest tasks a pet is missing, using only those guidelines. Each suggestion shows the guideline it came from and a confidence score, and nothing reaches the schedule until I click "Add".

It matters to me because a planner is only as good as the tasks you give it. Most owners don't know whether their dog's routine is missing dental care or heartworm prevention. Grounding the AI in written guidelines, and checking its output in code, means the suggestions can be traced to a source instead of being a model's guess.

## Architecture Overview

The full diagram is in [`diagrams/system_diagram.mmd`](diagrams/system_diagram.mmd) (Mermaid source), and the class diagram is in [`diagrams/uml.mmd`](diagrams/uml.mmd).

```
Owner ──> Streamlit UI (app.py) ──> Owner / Pet / Task ──> Scheduler ──> daily plan + conflict warnings

"Suggest tasks" click:
  Pet species + tasks ──> Retriever ──reads──> knowledge/{dog,cat,other}.md
        │
        └─ numbered guidelines (every topic covered) ──> Prompt ──> Gemini
                                                                      │
                          Validator (fields, real citation, no duplicates, confidence >= 0.5)
                                │ passes                              │ fails
                                ▼                                     ▼
                    UI: suggestion + source + confidence      dropped and logged
                                │
                       Owner clicks "Add" ──> Pet.add_task() ──> Scheduler
```

- **Data model** (`diagrams/pawpal_system.py`): `Task`, `Pet`, `Owner` and `Scheduler`. The scheduler orders pending tasks by priority within the minutes available, can re-sort by clock time, flags tasks at the same date and time across pets, filters by pet or status, and creates the next occurrence of daily and weekly tasks.
- **Retriever** (`retriever.py`): splits each guideline file into one chunk per bullet, tagged with its section, and returns the best chunks from every section by keyword overlap with the pet's tasks.
- **Suggester** (`suggester.py`): builds the prompt from the retrieved guidelines and the pet's tasks, calls Gemini, and validates every suggestion before the UI sees it.
- **Humans and tests:** the owner reviews each suggestion before it is added, the logs record what was retrieved and rejected, and the pytest suite checks the scheduler, retriever and validator.

## Setup Instructions

1. Clone the repository and go into the project folder.
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   ```
3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Get a free Gemini API key from Google AI Studio (aistudio.google.com, no credit card needed), then set it (needed only for the suggestion button):
   ```bash
   export GEMINI_API_KEY="your-key"       # Windows PowerShell: $env:GEMINI_API_KEY="your-key"
   ```
   The model defaults to `gemini-3.1-flash-lite`. Set `PAWPAL_MODEL` to use another one.
5. Run the app:
   ```bash
   streamlit run app.py
   ```
6. Optional: run the scheduler demo in the terminal with `python main.py`, try the retriever alone with `python retriever.py`, or run the full AI pipeline on three sample pets with `python demo_ai.py` (needs the API key).
7. Run the tests (no API key or network needed):
   ```bash
   python -m pytest
   ```

Without an API key the suggestion button shows a clear error and the rest of the app keeps working.

## Sample Interactions

Everything below is real output. Examples 1 and 2 are the retriever alone. Example 3 is the full RAG pipeline run live against Gemini (`python demo_ai.py`, saved in [`sample_run.txt`](sample_run.txt)) on three inputs. Example 4 is a real failure the guardrails handled, and example 5 is the scheduler.

**1. Retriever: dog exercise question**

Input: species `dog`, query `how long should the morning walk be`

```
[2] dog / Exercise - Puppies need short, frequent play sessions of 5 to 15 minutes rather than long walks.
[1] dog / Exercise - Most adult dogs need 30 to 60 minutes of walking or active exercise every day, split into one or two walks.
[1] dog / Exercise - Senior dogs benefit from shorter, gentler walks twice a day to protect their joints.
```

**2. Retriever: cat litter question**

Input: species `cat`, query `scoop litter box`

```
[3] cat / Litter box - Scoop the litter box at least once a day, and twice if possible.
[2] cat / Litter box - Fully replace the litter and wash the box every 1 to 2 weeks.
[2] cat / Litter box - Provide one litter box per cat, plus one extra.
```

**3. End-to-end RAG run on three inputs (live model)**

Inputs: Mochi the dog (walk, feeding), Luna the cat (litter box), and Biscuit the hamster (feeding). There is no hamster guideline file, so the third case exercises the fallback to general guidelines. For each pet the pipeline retrieves guidelines, asks the model for suggestions that cite a guideline, validates them, adds the accepted ones (standing in for the owner clicking "Add"), and finally builds one schedule from everything.

```
Model: gemini-3.1-flash-lite

=== Case 1: Mochi (dog) ===
Existing tasks: Morning walk, Feeding
Retrieved 10 guideline(s); topics: Enrichment, Exercise, Feeding, Grooming, Health
ACCEPTED: Evening walk for exercise | 30 min, high, daily at 18:00 | source: dog / Exercise | confidence 100%
          guideline: Most adult dogs need 30 to 60 minutes of walking or active exercise every day, split into one or two walks.
ACCEPTED: Second daily feeding | 10 min, high, daily at 18:00 | source: dog / Feeding | confidence 100%
          guideline: Adult dogs should be fed twice a day, roughly 8 to 12 hours apart.
ACCEPTED: Mental stimulation session | 15 min, medium, daily at 14:00 | source: dog / Enrichment | confidence 100%
          guideline: Dogs need daily mental stimulation such as training, puzzle feeders, or play for 10 to 15 minutes.
ACCEPTED: Monthly preventative medication | 5 min, high, once at 09:00 | source: dog / Health | confidence 100%
          guideline: Give flea, tick, and heartworm prevention medication monthly.
ACCEPTED: Annual veterinary checkup | 60 min, medium, once at 10:00 | source: dog / Health | confidence 100%
          guideline: Schedule a vet checkup at least once a year, and twice a year for senior dogs.

=== Case 2: Luna (cat) ===
Existing tasks: Litter box cleaning
Retrieved 11 guideline(s); topics: Enrichment, Exercise, Feeding, Grooming, Health, Litter box
ACCEPTED: Interactive play session with wand toy | 15 min, high, daily at 09:00 | source: cat / Exercise | confidence 100%
          guideline: Cats benefit from two or more interactive play sessions a day, each lasting 10 to 15 minutes.
ACCEPTED: Second interactive play session | 15 min, high, daily at 18:00 | source: cat / Exercise | confidence 100%
          guideline: Cats benefit from two or more interactive play sessions a day, each lasting 10 to 15 minutes.
ACCEPTED: Deep clean litter box and replace litter | 30 min, medium, weekly at 10:00 | source: cat / Litter box | confidence 100%
          guideline: Fully replace the litter and wash the box every 1 to 2 weeks.
ACCEPTED: Brush cat's fur | 10 min, medium, weekly at 11:00 | source: cat / Grooming | confidence 90%
          guideline: Brush short-haired cats weekly and long-haired cats daily to reduce hairballs.
ACCEPTED: Trim cat's nails | 15 min, low, weekly at 12:00 | source: cat / Grooming | confidence 90%
          guideline: Trim nails every 2 to 3 weeks.

=== Case 3: Biscuit (hamster) ===
Existing tasks: Feeding
LOG WARNING: No guidelines for species 'hamster'; falling back to 'other'
Retrieved 10 guideline(s); topics: Enrichment, Exercise, Feeding, Grooming, Habitat, Health
ACCEPTED: Provide supervised time outside the cage for exercise | 30 min, high, daily at 19:00 | source: other / Exercise | confidence 100%
          guideline: Every pet needs daily activity appropriate to its species, such as supervised time outside its cage or enclosure.
ACCEPTED: Refresh water supply | 2 min, high, daily at 08:00 | source: other / Feeding | confidence 100%
          guideline: Fresh water should be available at all times and refreshed daily.
ACCEPTED: Spot-clean the enclosure | 10 min, medium, daily at 09:00 | source: other / Habitat | confidence 100%
          guideline: Spot-clean the cage, tank, or enclosure daily, and do a full clean every 1 to 2 weeks.
ACCEPTED: Perform weekly health check of nails, coat, and teeth | 15 min, medium, weekly at 10:00 | source: other / Grooming | confidence 100%
          guideline: Check nails, coat, and teeth weekly, and groom as the species requires.
ACCEPTED: Add new toys or foraging activities | 5 min, low, weekly at 11:00 | source: other / Enrichment | confidence 100%
          guideline: Offer new toys, hiding spots, or foraging activities each week to prevent boredom.

=== Schedule built from original + accepted tasks (90 min budget) ===
Today's plan:
1. [2026-11-16 07:00] Morning walk for Mochi (30 min, priority: high)
2. [2026-11-16 18:00] Feeding for Mochi (10 min, priority: high)
3. [2026-11-16 18:00] Evening walk for exercise for Mochi (30 min, priority: high)
4. [2026-11-16 18:00] Second daily feeding for Mochi (10 min, priority: high)
5. [2026-11-16 09:00] Monthly preventative medication for Mochi (5 min, priority: high)
6. [2026-11-16 08:00] Refresh water supply for Biscuit (2 min, priority: high)
Scheduling conflicts:
- 2026-11-16 18:00: Feeding (Mochi), Evening walk for exercise (Mochi), Second daily feeding (Mochi), Second interactive play session (Luna)
- 2026-11-16 09:00: Monthly preventative medication (Mochi), Litter box cleaning (Luna), Interactive play session with wand toy (Luna), Spot-clean the enclosure (Biscuit)
- 2026-11-16 10:00: Annual veterinary checkup (Mochi), Deep clean litter box and replace litter (Luna), Perform weekly health check of nails, coat, and teeth (Biscuit)
- 2026-11-16 11:00: Brush cat's fur (Luna), Add new toys or foraging activities (Biscuit)
- 2026-11-16 08:00: Feeding (Biscuit), Refresh water supply (Biscuit)
```

What this shows:
- **Retrieval changes the output.** Every suggestion cites a retrieved guideline and quotes it, for example "Monthly preventative medication" for the dog comes from `dog / Health`, and the cat's nail trimming comes from `cat / Grooming`. The hamster case fell back to the general guidelines (see the `LOG WARNING` line) and its suggestions cite `other / ...` files.
- **Gaps were found.** The dog had no grooming, health or enrichment tasks, and the model filled in health and enrichment tasks from the guidelines it was given.
- **The AI output flows into the scheduler.** The accepted tasks went through the normal scheduler, and the conflict check then flagged several shared times, for example 18:00 for Mochi's feeding, an evening walk and a second feeding, plus Luna's play session. The model does not check clock times, and the scheduler's conflict detection catches that.
- **No suggestions were rejected in this run.** All 15 passed validation, so the rejection path is shown by the tests (table below), not by this run.

**4. A real failure handled by the guardrails**

The first time I ran the pipeline against the live API, the default model name had been retired for new users and the API returned a `404 NOT_FOUND`. The app did not crash. It logged the error and showed:

```
ERROR: Could not get AI suggestions (ClientError). Showing guidelines only.
```

The retrieved guidelines were still listed and the scheduler kept working. I then switched to a model my key can use. A later overloaded-model error (`503`) is handled the same way, and a 60-second request timeout stops it from hanging the UI.

**5. Scheduler: three tasks, one conflict** (from `python main.py`)

```
Today's Schedule (by priority)
1. [2026-10-19 18:00] Feeding for Mochi (10 min, priority: high)
2. [2026-10-19 07:00] Morning walk for Mochi (30 min, priority: high)
3. [2026-10-19 09:00] Litter box cleaning for Luna (5 min, priority: medium)
4. [2026-10-19 07:00] Brushing for Mochi (10 min, priority: low)

WARNING: Scheduling conflicts:
- 2026-10-19 07:00: Morning walk (Mochi), Brushing (Mochi), Vet checkup (Luna)
```

## Design Decisions

- **RAG over the other AI options.** Pet care has a natural knowledge source, and RAG changes what the system produces: the model sees the guidelines and the pet's tasks and answers from them. Fine-tuning needs training data I don't have, and an agentic workflow adds moving parts that are hard to keep reliable.
- **Hand-written knowledge files.** I wrote short bullets per species, so I know exactly what the AI can cite. The trade-off is that the guidelines are general and only as good as what I wrote. They are not veterinary advice.
- **Keyword matching, not embeddings.** With three small files, word overlap is easy to explain, test and debug, and needs no extra service. The trade-off is that it matches words, not meaning: "stroll" won't find "walk".
- **Retrieve from every topic, not just the top matches.** My first version returned the top few matches for the pet's task descriptions. Running it showed a problem: a dog with only a walk and a feeding got only exercise and feeding guidelines, so the model never saw the grooming or health guidelines it was supposed to notice were missing. I changed retrieval to return the best chunks from each section.
- **Validate in code, not by trusting the model.** Every suggestion must have valid fields, cite a guideline number that was actually retrieved, not duplicate an existing task, and carry a self-reported confidence of at least 0.5. The model's JSON is requested with a schema, but I still check every field.
- **A human in the loop.** Suggestions are never added automatically. The owner sees the source and confidence and clicks "Add", and an accepted task then goes through the normal scheduler.
- **Greedy scheduling and exact-time conflicts.** The scheduler adds tasks in priority order until time runs out, and flags only tasks that share the same date and time. Both are simple and predictable, at the cost of optimal packing and overlap detection.
- **Safe failure.** Unknown species fall back to general guidelines, the species name can only match existing filenames, and API errors, refusals, cut-off replies and malformed JSON all produce a message instead of a crash.

## Testing Summary

51 of 51 automated tests pass with `python -m pytest`: 9 for the scheduler, 12 for the retriever, and 30 for the suggestion step. The suggestion tests use a fake model client, so they need no API key or network.

| Test input | Evaluation criteria | Result |
|---|---|---|
| Sort tasks by time | Chronological order | Pass |
| Complete a daily task | New incomplete task due the next day | Pass |
| Complete a `once` task | No follow-up task | Pass |
| Same date and time across two pets | Conflict flagged | Pass |
| Same time on different dates | No conflict flagged | Pass |
| dog, "morning walk exercise" | Only dog chunks returned | Pass |
| cat, "scoop the litter box" | Top chunk is the "Litter box" section | Pass |
| dog, "quantum physics" | Returns nothing | Pass |
| species "hamster", `None`, or "../README" | Falls back to general guidelines, no crash, not used as a path | Pass |
| dog, by-topic retrieval | Every section (Exercise, Feeding, Grooming, Health, Enrichment) represented | Pass |
| Valid model reply | Suggestions accepted and grounded in the cited chunk | Pass |
| 15 invalid fields (bad duration, priority, frequency, time, citation, confidence) | Each rejected | Pass |
| Suggestion duplicating an existing task, or repeated in one reply | Dropped | Pass |
| Mixed good and bad suggestions | Good kept, bad dropped and counted | Pass |
| Invalid JSON, wrong JSON shape | Error message, no crash | Pass |
| API exception, refusal, truncated reply | Error message, guidelines still shown | Pass |
| No guidelines retrieved | No API call made | Pass |
| Accepted suggestion | Appears on the pet and flows into the scheduler | Pass |

**What worked:** the validation layer catches every kind of bad output I could think of, and failures are logged and shown as messages instead of crashing the app.

**What didn't, and what I fixed:** my first retrieval was biased toward topics the pet already had tasks for, which hid the very gaps the feature exists to find. I only noticed because I printed the prompt for a simple pet and read it. I fixed it with per-topic retrieval and added a test.

**Live evaluation (human review of the end-to-end run in example 3).** I read all 15 suggestions from `sample_run.txt` against the guideline each one cited:

| Evaluation criteria | Result |
|---|---|
| Suggestion is supported by the guideline it cites | 15 of 15 |
| All fields valid and accepted by the validator | 15 of 15 (0 rejected) |
| Frequency matches the guideline | 13 of 15. "Monthly preventative medication" was set to `once` because the app has no monthly option, and nail trimming "every 2 to 3 weeks" was set to `weekly`. |
| Suggestion avoids the clock time of an existing task | Partly. The model picked 18:00 for a second feeding and an evening walk even though Mochi's Feeding was already at 18:00, so the scheduler's conflict check flagged it. |
| Confidence score is informative | No. 13 of 15 were rated 100% and none below 90%, so it did not separate strong from weak suggestions. |

**Bugs only the live run found:** my tests all passed before the first live call, but the live run failed three times for reasons a fake client cannot catch. (1) I created the Gemini client inline, and it was cleaned up before the request finished ("client has been closed"), so I now keep a reference to it. (2) The default model name had been retired for new users and returned a `404`. (3) The newest model was overloaded and returned `503`, and a retry hung the app, so I added a 60-second timeout and switched to a model that responds in about a second.

**What the tests don't prove:**
- The automated tests check my code's handling of model output. The quality of real suggestions rests on the small manual review above (one run, three pets, one reviewer), which is not a statistical evaluation.
- The citation check confirms the cited guideline number was retrieved, not that the guideline actually supports the suggestion. The model could cite the wrong real guideline and pass.
- The confidence score is the model's own rating, not a calibrated measure.
- `build_schedule()` with a time budget of 0 and `filter_tasks()` still have no dedicated tests.

**What I learned:** reading the exact prompt the model receives is the fastest way to find retrieval problems, and a feature that sounds like AI is mostly ordinary code around the model call: retrieval, validation, and error handling.

## Reflection

This project taught me that adding AI makes the non-AI parts matter more. The suggestions are only useful because the scheduler already has clean, structured data to attach them to, and because the validator turns the model's free-form output into something the rest of the program can trust. It also changed how I think about "it works": a demo that looks right is not evidence, so I wrote down what each test does and does not prove. The biggest problem-solving lesson was to inspect the intermediate step, not just the final answer, which is how I found the retrieval bias. My responsible-AI reflection, covering how I worked with AI, a suggestion I accepted and one I rejected or revised, and the system's limitations, is in [`model_card.md`](model_card.md).
