# Model Card: PawPal+ Care Suggestions

## About the System

- **System:** PawPal+, a Streamlit pet care planner with an AI "care suggestions" feature.
- **Model used:** Google Gemini (`gemini-3.1-flash-lite` by default, set with the `PAWPAL_MODEL` environment variable), called through the `google-genai` Python SDK. I chose it because it has a free tier, which suits a course project.
- **What the AI does:** given a pet's species, its current tasks, and a numbered list of care guidelines retrieved from my own `knowledge/` files, it proposes up to 5 tasks the pet may be missing. Each proposal has a duration, priority, frequency, time, reason, the number of the guideline it relies on, and a self-rated confidence from 0 to 1.
- **What the AI does not do:** it does not build the schedule, detect conflicts, or add tasks. The Scheduler class does the first two, and the owner does the last by clicking "Add".
- **Intended use:** a pet owner planning routine care for a dog, cat, or other small pet. It is not for diagnosing illness, choosing medication or doses, or replacing a vet.

**Safeguards in the pipeline:**
1. The model only sees guidelines retrieved for the pet's species, with every care topic represented.
2. The system prompt tells it to use only those numbered guidelines, cite one per suggestion, and not repeat existing tasks.
3. Every suggestion is rejected in code unless it has valid fields, cites a guideline that was actually retrieved, is not a duplicate, and has confidence of at least 0.5.
4. Suggestions are only added when the owner clicks "Add".
5. Retrieval, rejections and errors are logged, and API errors, refusals and malformed replies show a message instead of crashing the app.

**Test results:** 51 automated tests pass (9 scheduler, 12 retriever, 30 suggestion step). The suggestion tests use a fake model client, so they show that my code handles good and bad output, not how good the model's real suggestions are. I also ran the full pipeline live against Gemini on three pets (`demo_ai.py`, output saved in `sample_run.txt`) and reviewed the 15 suggestions by hand; see the README's Testing Summary.

---

## 1. Limitations and Biases

- **The knowledge base is small and written by me.** It has 11 to 16 bullets per species and covers only dogs, cats and a generic "other" category. It is general guidance, not veterinary advice, and may be incomplete or wrong for a specific breed, age or health condition.
- **Species bias.** Dog and cat guidance is more detailed than the "other" file, so owners of rabbits, birds or reptiles get weaker, more generic suggestions. The guidelines also assume typical household pets and a typical adult animal unless stated otherwise.
- **Keyword retrieval matches words, not meaning.** A query using "stroll" will not find a guideline that says "walk", and ranking inside a topic can be imperfect.
- **Grounding is only partly checked.** The validator confirms that the cited guideline number was retrieved, not that the guideline really supports the suggestion. The model could cite a real but irrelevant guideline and still pass.
- **Confidence is self-reported and was not informative.** In my live run, 13 of 15 suggestions were rated 100% and none were below 90%, so the 0.5 cutoff never rejected anything. The score is not calibrated and is overconfident.
- **Live quality was checked only lightly.** I reviewed 15 live suggestions (three pets, one run, one reviewer) and found them supported by their cited guidelines, but that is far too small a sample to claim the suggestions are reliably good, and it was not run with a peer.
- **Limited task fields.** A task can only repeat once, daily or weekly, so "monthly" medication and "every 2 to 3 weeks" nail trims were squeezed into `once` and `weekly`.
- **The model ignores clock times.** It proposed new tasks at times already used by the pet's existing tasks, so owners get conflicts to resolve. The scheduler flags these, but the suggester does not avoid them.
- **The scheduler is simple.** It packs tasks greedily by priority and flags only exact same-time conflicts, not overlapping durations, so it can miss a near-overlap or choose a non-optimal set of tasks.
- **Model variability.** The same pet can get different suggestions on different runs, and model or API changes can change behavior.

## 2. Could the AI Be Misused, and How Do I Prevent It?

| Risk | How I prevent or reduce it | What remains |
|---|---|---|
| An owner treats a suggestion as medical advice, for example about medication or a sick pet | Suggestions come only from my general guidelines, show their source and confidence, and need a click to add. The knowledge files contain no dosing or treatment advice, only routine care. | The UI has no "consult your vet" notice yet. I should add one. |
| The model invents advice that is not in the guidelines | The prompt restricts it to the numbered guidelines, a citation must match a retrieved guideline, bad fields are rejected, and a confidence threshold applies. | A real but wrongly matched citation can still pass. |
| Someone types instructions into a pet or task name to steer the model (prompt injection) | The output is constrained to a JSON schema and every field is validated, so the model cannot add arbitrary tasks, and nothing is added without the owner clicking "Add". | Free text in a task name still reaches the prompt, and a malicious name could skew the suggestions. |
| Personal data leaves the app | The prompt contains only the pet's name, species, task names and guideline text, and the API key is read from an environment variable, not stored in the code. | Pet names and tasks are sent to Google's Gemini API, so owners should not put sensitive details in task names. |
| Unsafe input in the species field | The species name can only match existing guideline filenames, so it can never be used as a file path. | None known. |
| API outage, refusal or bad JSON | Errors are caught, logged and shown as messages, and the rest of the app keeps working. | The suggestion feature is unavailable until the API recovers. |
| Using the tool outside its purpose, such as for livestock or exotic animals | The "other" category uses deliberately generic guidance. | The tool cannot tell when a species is poorly covered. |

## 3. What Surprised Me While Testing the AI's Reliability

- **My retrieval hid the gaps the feature exists to find.** My first retriever returned the top matches for the pet's existing task descriptions. When I printed the prompt for a dog with only "Morning walk" and "Feeding", it contained only exercise and feeding guidelines, so the model could never have suggested grooming or health tasks. All my retriever tests passed at that point, because they checked that results were on topic, not that the right topics were present. I only found it by reading the prompt, and I fixed it by retrieving from every topic and adding a test for that.
- **The validator accepted a mismatched citation.** In a scripted reply, I had "Brush teeth" cite a guideline about puppy exercise, and the validator accepted it, because the check only confirms that the cited number was retrieved. I had assumed "must cite a retrieved guideline" meant "is supported by a guideline". It doesn't, and this is now listed as a limitation instead of a claim.
- **Ranking was less sensible than it looked.** For "how long should the morning walk be", the puppy guideline outranked the adult one, because it shared more words with the question. The retrieval was working as designed and still gave a worse answer, which showed me that keyword overlap is not relevance.
- **Every test passed, and the first live call still failed three times.** My automated tests all passed before I ever called the real API, then the live run hit three problems a fake client cannot show: a client object cleaned up before the request finished, a default model name that had been retired for new users (`404`), and an overloaded model (`503`) that made the app hang until I added a timeout and picked a different model. Testing against a stand-in proved my logic, not the integration.
- **The model was well grounded but too sure of itself.** All 15 live suggestions were supported by the guideline they cited, which was better than I expected, yet 13 were rated 100% confident. A confidence score that never varies cannot be used to filter anything.
- **Most of the reliability work was ordinary code.** I expected the hard part to be the AI call. Most of the effort, and most of the tests, went into validation and error handling around it. Every kind of bad output I could think of had to be handled before I could trust the feature.

## 4. Collaboration with AI

**How I used AI.** I used Claude Code throughout this course project. In Module 2 it helped turn my class descriptions into the UML diagram, generate the Python skeleton, implement the scheduling logic, write the demo and unit tests, and draft the README. For this extension I asked it which AI feature best fit the project, and it recommended RAG and explained why. It then helped build the retriever, the suggestion step, the tests, the diagram and the documentation. Claude Code also helped me switch the suggestion step from Claude to Gemini, because I could not pay for an API key, by isolating the model call behind one small function. It was most useful when it read my existing files before suggesting changes, so its code matched my real method signatures, and when it ran the tests in the same conversation so I could see real output.

### A suggestion I accepted

In Module 2, the AI wrote `Scheduler.build_schedule()` using the `dict | None` type-hint syntax. When I ran the code in my own environment (Python 3.9), it crashed with a `TypeError`, because that syntax needs Python 3.10 or later. The AI proposed adding `from __future__ import annotations`. I accepted that fix, but only after re-running `main.py` and the tests myself and seeing the crash go away. I accepted it because it was a one-line change that fixed the real cause without changing the code's behavior.

I also accepted the AI's recommendation to add RAG with a validation layer instead of fine-tuning or an agentic workflow. It fit the project because pet care has a natural knowledge source, and it kept the system small enough for me to explain and test.

### A suggestion I did not accept as written

While wiring the Streamlit UI to the scheduler, the easy approach was to call `build_schedule()` automatically on every page rerun, so the schedule and conflict warnings would always be live. I did not accept that, because it would make the "Generate schedule" and "Sort by time" buttons pointless and could reorder tasks without being asked. I changed it so scheduling only runs when the user clicks the button, and only the conflict check is live, because checking for conflicts doesn't change any state.

I also revised the AI's first retrieval design for this extension. It returned the top-matching chunks for the pet's task descriptions, which was simple and readable but a poor fit for the goal of finding missing tasks (see section 3). I kept the keyword approach, since it was easy to test, and changed only what it returns: the best chunks from every topic. I rejected the heavier alternative of switching to embeddings, because it would add a dependency and make the retrieval harder to explain for a problem that was really about coverage.

### What I learned about working with AI

The AI is fast at implementing something once I describe it, and good at catching broken sorts and missing edge cases, but it does not know which trade-offs matter for my scenario unless I tell it. It also sometimes reported something as working before it had been checked in my environment, which is why I verified each change myself and read the exact prompt the model receives. My role ended up being less writing every line and more deciding what correct behavior is, running everything, and asking the AI to explain when something looked off.

## 5. Future Improvements

- Expand the human evaluation of live suggestions to more pets and a peer reviewer, and compare confidence scores against the ratings.
- Add a monthly frequency, and tell the model which times are already taken so it avoids conflicts.
- Check that the cited guideline really supports the suggestion, for example by requiring the suggestion to quote the guideline text.
- Add a vet-consultation notice to the suggestion UI.
- Expand and review the knowledge base, ideally with input from a veterinarian, and add more species.
- Improve retrieval with synonyms.
- Add tests for `build_schedule()` edge cases and `filter_tasks()`.
