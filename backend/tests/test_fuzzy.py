"""Tests for fuzzy string matching utilities."""

from __future__ import annotations

import pytest

from app.utils.fuzzy import (
    jaro_winkler_similarity,
    levenshtein_distance,
    levenshtein_similarity,
    name_matches,
    normalise_name,
)


class TestLevenshtein:
    """Tests for Levenshtein distance and similarity."""

    def test_identical_strings(self) -> None:
        assert levenshtein_distance("hello", "hello") == 0
        assert levenshtein_similarity("hello", "hello") == 1.0

    def test_completely_different(self) -> None:
        assert levenshtein_distance("abc", "xyz") == 3
        assert levenshtein_similarity("abc", "xyz") == 0.0

    def test_one_insertion(self) -> None:
        assert levenshtein_distance("cat", "cats") == 1

    def test_one_substitution(self) -> None:
        assert levenshtein_distance("cat", "cut") == 1

    def test_one_deletion(self) -> None:
        assert levenshtein_distance("cats", "cat") == 1

    def test_empty_strings(self) -> None:
        assert levenshtein_distance("", "") == 0
        assert levenshtein_similarity("", "") == 1.0
        assert levenshtein_distance("abc", "") == 3

    def test_similarity_partial(self) -> None:
        # "kitten" -> "sitting" has distance 3
        sim = levenshtein_similarity("kitten", "sitting")
        assert 0.5 < sim < 1.0


class TestJaroWinkler:
    """Tests for Jaro-Winkler similarity."""

    def test_identical(self) -> None:
        assert jaro_winkler_similarity("john", "john") == 1.0

    def test_common_prefix_bonus(self) -> None:
        # "MARTHA" vs "MARHTA" — high similarity with prefix bonus
        sim = jaro_winkler_similarity("MARTHA", "MARHTA")
        assert sim > 0.9

    def test_different_strings(self) -> None:
        sim = jaro_winkler_similarity("DWAYNE", "DUANE")
        assert sim > 0.8

    def test_very_different(self) -> None:
        sim = jaro_winkler_similarity("abc", "xyz")
        assert sim < 0.5

    def test_empty_strings(self) -> None:
        assert jaro_winkler_similarity("", "") == 1.0
        assert jaro_winkler_similarity("abc", "") == 0.0


class TestNameNormalisation:
    """Tests for name normalisation."""

    def test_lowercase(self) -> None:
        assert normalise_name("John Doe") == "doe john"

    def test_strip_titles(self) -> None:
        assert normalise_name("Mr John Doe") == "doe john"
        assert normalise_name("Dr Jane Smith") == "jane smith"

    def test_strip_suffixes(self) -> None:
        assert normalise_name("John Doe Jr") == "doe john"
        assert normalise_name("John Smith III") == "john smith"

    def test_remove_punctuation(self) -> None:
        assert normalise_name("O'Brien") == "obrien"
        # Hyphenated names keep the hyphen
        assert normalise_name("Smith-Jones") == "smith-jones"

    def test_sorted_tokens(self) -> None:
        # "Doe John" and "John Doe" should normalise to the same thing
        assert normalise_name("Doe John") == normalise_name("John Doe")

    def test_empty_string(self) -> None:
        assert normalise_name("") == ""
        assert normalise_name("   ") == ""


class TestNameMatches:
    """Tests for the high-level name_matches function."""

    def test_exact_match_jaro_winkler(self) -> None:
        is_match, score, matched = name_matches(
            "John Doe", "John Doe", method="jaro_winkler", threshold=0.88
        )
        assert is_match
        assert score >= 0.95
        assert matched == "John Doe"

    def test_exact_match_levenshtein(self) -> None:
        is_match, score, matched = name_matches(
            "John Doe", "John Doe", method="levenshtein", threshold=0.88
        )
        assert is_match
        assert score >= 0.95

    def test_close_match(self) -> None:
        is_match, score, matched = name_matches(
            "Jon Doe", "John Doe", method="jaro_winkler", threshold=0.85
        )
        assert is_match

    def test_no_match(self) -> None:
        is_match, score, matched = name_matches(
            "Alice Wonderland",
            "Bob Smith",
            method="jaro_winkler",
            threshold=0.88,
        )
        assert not is_match

    def test_with_variations(self) -> None:
        is_match, score, matched = name_matches(
            "Jonny",
            "Johnathan Doe",
            method="jaro_winkler",
            threshold=0.7,
            candidate_variations=["Jonny", "Jon"],
        )
        assert is_match
        assert matched == "Jonny"

    def test_swapped_names(self) -> None:
        """Normalisation should handle swapped first/last names."""
        is_match, score, matched = name_matches(
            "Doe John", "John Doe", method="jaro_winkler", threshold=0.95
        )
        assert is_match

    def test_low_threshold_no_match(self) -> None:
        is_match, score, matched = name_matches(
            "Alice", "Bob", method="jaro_winkler", threshold=0.95
        )
        assert not is_match