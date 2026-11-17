"""Simple keyword-based retriever over the pet care guideline files in knowledge/.

Each bullet in a guideline file becomes one chunk, tagged with its species file
and the section heading it appeared under. Chunks are ranked by how many query
words they share (after light normalization). No embeddings or external
services are needed.
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"
DEFAULT_SPECIES = "other"

# Words too common to help ranking.
STOPWORDS = {
    "a", "an", "and", "the", "to", "of", "for", "or", "in", "on", "at", "is",
    "are", "be", "it", "its", "as", "with", "by", "per", "each", "every",
    "this", "that", "than", "from", "so", "if", "my", "your",
}


@dataclass(frozen=True)
class Chunk:
    species: str
    topic: str
    text: str
    score: int = 0

    def citation(self) -> str:
        return f"{self.species} / {self.topic}"


def _normalize(word: str) -> str:
    """Lowercase and strip a trailing plural 's' so 'walks' matches 'walk'."""
    word = word.lower()
    if len(word) > 3 and word.endswith("s"):
        word = word[:-1]
    return word


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z]+", text)
    return {_normalize(w) for w in words if w.lower() not in STOPWORDS}


def available_species() -> list[str]:
    """Species names that have a guideline file (e.g. ['cat', 'dog', 'other'])."""
    return sorted(p.stem for p in KNOWLEDGE_DIR.glob("*.md"))


def load_chunks(species: str) -> list[Chunk]:
    """Load every bullet from the species' file; unknown species fall back to 'other'.

    The species is only ever matched against existing filenames, so user input
    can never be used to read arbitrary paths.
    """
    key = (species or "").strip().lower()
    if key not in available_species():
        logger.warning("No guidelines for species %r; falling back to %r", species, DEFAULT_SPECIES)
        key = DEFAULT_SPECIES

    path = KNOWLEDGE_DIR / f"{key}.md"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logger.error("Could not read %s: %s", path, exc)
        return []

    chunks: list[Chunk] = []
    topic = "general"
    for line in lines:
        line = line.strip()
        if line.startswith("## "):
            topic = line[3:].strip()
        elif line.startswith("- "):
            chunks.append(Chunk(species=key, topic=topic, text=line[2:].strip()))
    return chunks


def get_guidelines(species: str, query: str = "", top_k: int = 3) -> list[Chunk]:
    """Return the top_k guideline chunks for a species that best match the query.

    Each chunk is scored by the number of query words found in its text or topic.
    Chunks with no overlap are dropped, so an unrelated query returns [].
    With an empty query, the first top_k chunks are returned unscored.
    """
    chunks = load_chunks(species)
    query_words = _tokenize(query)

    if not query_words:
        results = chunks[:top_k]
    else:
        scored = []
        for chunk in chunks:
            score = len(query_words & _tokenize(f"{chunk.topic} {chunk.text}"))
            if score > 0:
                scored.append(Chunk(chunk.species, chunk.topic, chunk.text, score))
        # Highest score first; ties keep file order (sort is stable).
        scored.sort(key=lambda c: c.score, reverse=True)
        results = scored[:top_k]

    logger.info(
        "Retrieved %d chunk(s) for species=%r query=%r", len(results), species, query
    )
    return results


def get_guidelines_by_topic(species: str, query: str = "", per_topic: int = 2) -> list[Chunk]:
    """Return the best `per_topic` chunks from every section of a species' guidelines.

    Plain top-k retrieval favors topics the pet already has tasks for, which hides
    exactly the gaps (grooming, health, ...) the suggester is meant to find. This
    guarantees every topic is represented, ranked by query match within each one.
    """
    query_words = _tokenize(query)
    by_topic: dict[str, list[Chunk]] = {}
    for chunk in load_chunks(species):
        score = len(query_words & _tokenize(f"{chunk.topic} {chunk.text}"))
        by_topic.setdefault(chunk.topic, []).append(
            Chunk(chunk.species, chunk.topic, chunk.text, score)
        )

    results: list[Chunk] = []
    for chunks in by_topic.values():
        results.extend(sorted(chunks, key=lambda c: c.score, reverse=True)[:per_topic])

    logger.info(
        "Retrieved %d chunk(s) across %d topic(s) for species=%r", len(results), len(by_topic), species
    )
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for chunk in get_guidelines("dog", "how long should the morning walk be"):
        print(f"[{chunk.score}] ({chunk.citation()}) {chunk.text}")
