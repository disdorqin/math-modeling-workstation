from __future__ import annotations

import pandas as pd

from mathworkstation.word_features import (
    augment_word_features,
    future_word_features,
    word_feature_vector,
    wordle_task_feature_sets,
)


def test_word_features_capture_repetition_and_use_same_future_schema() -> None:
    frame = pd.DataFrame({"Word": ["raise", "eerie", "judge", "molar"]})

    augmented, frequencies, columns = augment_word_features(frame, "Word")
    eerie = future_word_features("EERIE", frequencies)

    assert set(columns) == set(eerie)
    row = augmented.loc[1]
    assert row["word_word_length"] == 5
    assert row["word_vowel_count"] == 4
    assert row["word_unique_letter_count"] == 3
    assert row["word_repeated_letter_count"] == 2
    assert row["word_max_letter_multiplicity"] == 3
    assert eerie["word_repeated_letter_count"] == 2
    assert row["word_positional_letter_surprisal"] > 0
    assert row["word_letter_transition_surprisal"] > 0
    assert eerie["word_positional_letter_surprisal"] > 0
    assert eerie["word_letter_transition_surprisal"] > 0


def test_word_feature_vector_does_not_require_external_dictionary() -> None:
    frequencies = {"a": 0.4, "b": 0.3, "c": 0.2, "z": 0.1}
    features = word_feature_vector("abaca", frequencies)

    assert features["word_length"] == 5
    assert features["unique_letter_count"] == 3
    assert features["repeated_letter_count"] == 2
    assert features["rare_letter_score"] > 0
    assert features["positional_letter_surprisal"] > 0
    assert features["letter_transition_surprisal"] > 0


def test_wordle_feature_sets_are_task_specific_after_real_ablation() -> None:
    sets = wordle_task_feature_sets()

    assert "word_positional_letter_surprisal" not in sets["SP1"]
    assert "word_positional_letter_surprisal" in sets["SP2"]
    assert "word_letter_transition_surprisal" not in sets["SP2"]
    assert "word_positional_letter_surprisal" in sets["SP3"]
    assert "word_letter_transition_surprisal" in sets["SP3"]
    assert "word_positional_letter_surprisal" not in sets["SP4"]
    assert "word_letter_transition_surprisal" not in sets["SP4"]
