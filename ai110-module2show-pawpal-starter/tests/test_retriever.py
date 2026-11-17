import logging

from retriever import available_species, get_guidelines, load_chunks


def test_all_species_files_load_with_chunks():
    for species in ("dog", "cat", "other"):
        assert species in available_species()
        assert len(load_chunks(species)) > 0


def test_dog_query_returns_only_dog_guidelines():
    results = get_guidelines("dog", "morning walk exercise")
    assert results
    assert all(c.species == "dog" for c in results)


def test_cat_litter_query_finds_litter_box_section():
    results = get_guidelines("cat", "scoop the litter box")
    assert results
    assert results[0].topic == "Litter box"


def test_results_ranked_best_first_and_limited_by_top_k():
    results = get_guidelines("dog", "walk exercise", top_k=2)
    assert len(results) <= 2
    scores = [c.score for c in results]
    assert scores == sorted(scores, reverse=True)


def test_plural_words_match_singular():
    assert get_guidelines("dog", "walks")


def test_unrelated_query_returns_nothing():
    assert get_guidelines("dog", "quantum physics") == []


def test_empty_query_returns_top_k_unscored():
    results = get_guidelines("cat", "", top_k=3)
    assert len(results) == 3


def test_unknown_species_falls_back_to_other_and_logs(caplog):
    with caplog.at_level(logging.WARNING):
        results = get_guidelines("hamster", "feeding")
    assert results
    assert all(c.species == "other" for c in results)
    assert "falling back" in caplog.text


def test_path_traversal_species_is_rejected():
    results = get_guidelines("../README", "feeding")
    assert all(c.species == "other" for c in results)


def test_none_species_does_not_crash():
    assert isinstance(get_guidelines(None, "feeding"), list)


def test_by_topic_covers_every_section_even_without_matching_query():
    from retriever import get_guidelines_by_topic

    topics = {c.topic for c in get_guidelines_by_topic("dog", "morning walk")}
    assert {"Exercise", "Feeding", "Grooming", "Health", "Enrichment"} <= topics


def test_by_topic_limits_chunks_per_topic_and_ranks_matches_first():
    from collections import Counter
    from retriever import get_guidelines_by_topic

    results = get_guidelines_by_topic("cat", "litter box", per_topic=2)
    assert max(Counter(c.topic for c in results).values()) <= 2
    litter = [c for c in results if c.topic == "Litter box"]
    assert litter and litter[0].score > 0
