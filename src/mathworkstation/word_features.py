from __future__ import annotations

from collections import Counter
from typing import Iterable

import numpy as np
import pandas as pd


BASE_WORD_FEATURE_COLUMNS = [
    "word_length",
    "vowel_count",
    "unique_letter_count",
    "repeated_letter_count",
    "max_letter_multiplicity",
    "mean_corpus_letter_frequency",
    "min_corpus_letter_frequency",
    "rare_letter_score",
]

# Domain-specific constructs derived only from the contest word corpus. These
# quantify how surprising a word is under (a) position-specific letter usage
# and (b) first-order letter transitions. They are intentionally distinct from
# dictionary popularity/familiarity, which would require an external source.
DOMAIN_WORD_FEATURE_COLUMNS = [
    "positional_letter_surprisal",
    "letter_transition_surprisal",
]

WORD_FEATURE_COLUMNS = [*BASE_WORD_FEATURE_COLUMNS, *DOMAIN_WORD_FEATURE_COLUMNS]


def prefixed_word_feature_columns(names: Iterable[str], *, prefix: str = "word_") -> list[str]:
    return [f"{prefix}{name}" for name in names]


def wordle_task_feature_sets(*, prefix: str = "word_") -> dict[str, list[str]]:
    """Feature sets accepted by the current Wordle ablation Gate.

    Domain constructs are intentionally task-specific. The positional surprisal
    is retained for explanatory inference; both surprisal features are retained
    for distribution forecasting; classification keeps the simpler base set
    because the added features did not improve robust multi-seed validation.
    """

    base = prefixed_word_feature_columns(BASE_WORD_FEATURE_COLUMNS, prefix=prefix)
    positional = f"{prefix}positional_letter_surprisal"
    transition = f"{prefix}letter_transition_surprisal"
    return {
        "SP1": list(base),
        "SP2": [*base, positional],
        "SP3": [*base, positional, transition],
        "SP4": list(base),
        "SP5": [*base, positional, transition],
    }


def corpus_letter_frequencies(words: Iterable[str]) -> dict[str, float]:
    """Estimate letter frequencies using only the supplied contest word corpus."""

    counts: Counter[str] = Counter()
    total = 0
    for raw in words:
        word = _normalize_word(raw)
        counts.update(word)
        total += len(word)
    if total == 0:
        raise ValueError("WORD_CORPUS_EMPTY")
    return {letter: count / total for letter, count in counts.items()}


def corpus_lexical_statistics(words: Iterable[str]) -> dict[str, float]:
    """Build smoothed lexical statistics from the supplied contest word corpus.

    Plain single-letter frequencies retain their historical keys for backward
    compatibility. Namespaced keys store position probabilities and first-order
    transition probabilities used by the Wordle-specific surprisal features.
    """

    normalized = [_normalize_word(value) for value in words]
    if not normalized:
        raise ValueError("WORD_CORPUS_EMPTY")
    stats = corpus_letter_frequencies(normalized)
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    alpha = 0.5
    max_length = max(len(word) for word in normalized)
    for position in range(max_length):
        letters = [word[position] for word in normalized if len(word) > position]
        counts = Counter(letters)
        denominator = len(letters) + alpha * len(alphabet)
        for letter in alphabet:
            stats[f"__pos__{position}:{letter}"] = (counts.get(letter, 0) + alpha) / denominator

    transition_counts: Counter[tuple[str, str]] = Counter()
    previous_counts: Counter[str] = Counter()
    for word in normalized:
        for left, right in zip(word, word[1:]):
            transition_counts[(left, right)] += 1
            previous_counts[left] += 1
    for left in alphabet:
        denominator = previous_counts.get(left, 0) + alpha * len(alphabet)
        for right in alphabet:
            stats[f"__trans__{left}>{right}"] = (
                transition_counts.get((left, right), 0) + alpha
            ) / denominator
    return stats


def word_feature_vector(word: str, letter_frequencies: dict[str, float]) -> dict[str, float]:
    normalized = _normalize_word(word)
    counts = Counter(normalized)
    vowels = set("aeiou")
    frequencies = [float(letter_frequencies.get(letter, 0.0)) for letter in normalized]
    positive = [value for value in frequencies if value > 0]
    floor = min(positive) if positive else 1e-6
    safe_frequencies = [value if value > 0 else floor * 0.5 for value in frequencies]
    rare_score = float(np.mean([-np.log(max(value, 1e-12)) for value in safe_frequencies]))
    positional_probabilities = [
        float(letter_frequencies.get(f"__pos__{position}:{letter}", letter_frequencies.get(letter, floor * 0.5)))
        for position, letter in enumerate(normalized)
    ]
    positional_surprisal = float(
        np.mean([-np.log(max(value, 1e-12)) for value in positional_probabilities])
    )
    transition_probabilities = [
        float(letter_frequencies.get(f"__trans__{left}>{right}", letter_frequencies.get(right, floor * 0.5)))
        for left, right in zip(normalized, normalized[1:])
    ]
    transition_surprisal = float(
        np.mean([-np.log(max(value, 1e-12)) for value in transition_probabilities])
        if transition_probabilities
        else 0.0
    )
    return {
        "word_length": float(len(normalized)),
        "vowel_count": float(sum(letter in vowels for letter in normalized)),
        "unique_letter_count": float(len(counts)),
        "repeated_letter_count": float(sum(max(0, count - 1) for count in counts.values())),
        "max_letter_multiplicity": float(max(counts.values())),
        "mean_corpus_letter_frequency": float(np.mean(safe_frequencies)),
        "min_corpus_letter_frequency": float(np.min(safe_frequencies)),
        "rare_letter_score": rare_score,
        "positional_letter_surprisal": positional_surprisal,
        "letter_transition_surprisal": transition_surprisal,
    }


def augment_word_features(
    frame: pd.DataFrame,
    word_column: str,
    *,
    prefix: str = "word_",
) -> tuple[pd.DataFrame, dict[str, float], list[str]]:
    if word_column not in frame.columns:
        raise ValueError(f"WORD_COLUMN_MISSING:{word_column}")
    frequencies = corpus_lexical_statistics(frame[word_column].astype(str).tolist())
    records = [word_feature_vector(value, frequencies) for value in frame[word_column].astype(str)]
    feature_frame = pd.DataFrame(records, index=frame.index)
    renamed = {column: f"{prefix}{column}" for column in WORD_FEATURE_COLUMNS}
    feature_frame = feature_frame.rename(columns=renamed)
    output = pd.concat([frame.copy(), feature_frame], axis=1)
    columns = [renamed[column] for column in WORD_FEATURE_COLUMNS]
    return output, frequencies, columns


def future_word_features(
    word: str,
    letter_frequencies: dict[str, float],
    *,
    prefix: str = "word_",
) -> dict[str, float]:
    return {f"{prefix}{key}": value for key, value in word_feature_vector(word, letter_frequencies).items()}


def _normalize_word(value: object) -> str:
    word = "".join(character for character in str(value).strip().lower() if character.isalpha())
    if not word:
        raise ValueError("WORD_VALUE_EMPTY")
    return word
