"""AML Monitor — Fuzzy string matching utilities.

Provides Levenshtein distance, Jaro-Winkler similarity, and a
configurable name-matching function for sanctions screening.
"""

from __future__ import annotations

import re
from typing import Sequence

# ---------------------------------------------------------------------------
# Levenshtein distance
# ---------------------------------------------------------------------------


def levenshtein_distance(s1: str, s2: str) -> int:
    """Compute the Levenshtein (edit) distance between two strings.

    The distance is the minimum number of single-character edits
    (insertions, deletions, substitutions) required to change *s1* into *s2*.
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr.append(
                min(
                    curr[j] + 1,          # deletion
                    prev[j + 1] + 1,      # insertion
                    prev[j] + cost,       # substitution
                )
            )
        prev = curr

    return prev[-1]


def levenshtein_similarity(s1: str, s2: str) -> float:
    """Return a normalised similarity score in [0.0, 1.0].

    1.0 means identical strings; 0.0 means completely different.
    """
    if not s1 and not s2:
        return 1.0
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0
    return 1.0 - (levenshtein_distance(s1, s2) / max_len)


# ---------------------------------------------------------------------------
# Jaro-Winkler similarity
# ---------------------------------------------------------------------------


def _jaro_similarity(s1: str, s2: str) -> float:
    """Compute the Jaro similarity between two strings."""
    if s1 == s2:
        return 1.0

    len1, len2 = len(s1), len(s2)
    match_distance = max(len1, len2) // 2 - 1
    if match_distance < 0:
        match_distance = 0

    s1_matches = [False] * len1
    s2_matches = [False] * len2

    matches = 0
    transpositions = 0

    for i in range(len1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len2)

        for j in range(start, end):
            if s2_matches[j] or s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    k = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while k < len2 and not s2_matches[k]:
            k += 1
        if k < len2 and s1[i] != s2[k]:
            transpositions += 1
        k += 1

    transpositions //= 2

    return (
        (matches / len1)
        + (matches / len2)
        + ((matches - transpositions) / matches)
    ) / 3.0


def jaro_winkler_similarity(s1: str, s2: str, prefix_scale: float = 0.1) -> float:
    """Compute the Jaro-Winkler similarity.

    This variant gives a higher score to strings that share a common prefix.
    *prefix_scale* is the scaling factor (typically 0.1).
    """
    jaro = _jaro_similarity(s1, s2)

    # Count common prefix (max 4 characters)
    prefix_len = 0
    for i in range(min(len(s1), len(s2), 4)):
        if s1[i] == s2[i]:
            prefix_len += 1
        else:
            break

    return jaro + (prefix_len * prefix_scale * (1.0 - jaro))


# ---------------------------------------------------------------------------
# Name normalisation
# ---------------------------------------------------------------------------

# Common name prefixes / titles to strip during comparison
_TITLES = {
    "mr", "mrs", "ms", "miss", "dr", "prof", "sir", "lord",
    "lady", "dame", "capt", "col", "gen", "lt", "maj", "cpt",
    "sheikh", "hajji", "haji", "haj",
}

# Common suffixes
_SUFFIXES = {
    "jr", "sr", "ii", "iii", "iv", "v", "md", "phd", "esq",
}


def normalise_name(name: str) -> str:
    """Normalise a name for comparison.

    - Lowercases
    - Strips titles and suffixes
    - Removes punctuation
    - Collapses whitespace
    - Sorts tokens alphabetically (to handle swapped first/last names)
    """
    name = name.lower().strip()
    # Remove punctuation (keep only letters, spaces, and hyphens)
    name = re.sub(r"[^a-z\-\s]", "", name)
    # Split into tokens
    tokens = name.split()
    # Remove titles and suffixes
    tokens = [t for t in tokens if t not in _TITLES and t not in _SUFFIXES]
    # Sort tokens so "John Doe" matches "Doe John"
    tokens = sorted(tokens)
    return " ".join(tokens)


# ---------------------------------------------------------------------------
# High-level matcher
# ---------------------------------------------------------------------------


def name_matches(
    query_name: str,
    candidate_name: str,
    *,
    method: str = "jaro_winkler",
    threshold: float = 0.88,
    candidate_variations: Sequence[str] | None = None,
) -> tuple[bool, float, str]:
    """Check whether *query_name* matches *candidate_name*.

    Parameters
    ----------
    query_name:
        The name to look up (e.g. a client or transaction party).
    candidate_name:
        The name from the sanctions list.
    method:
        ``"jaro_winkler"`` (default) or ``"levenshtein"``.
    threshold:
        Similarity threshold above which a match is declared.
    candidate_variations:
        Optional list of aliases / name variations for the candidate.

    Returns
    -------
    Tuple of ``(is_match, score, matched_name)``.
    """
    names_to_check = [candidate_name]
    if candidate_variations:
        names_to_check.extend(candidate_variations)

    query_norm = normalise_name(query_name)

    for raw_name in names_to_check:
        cand_norm = normalise_name(raw_name)

        if method == "levenshtein":
            score = levenshtein_similarity(query_norm, cand_norm)
        else:
            score = jaro_winkler_similarity(query_norm, cand_norm)

        if score >= threshold:
            return True, round(score, 4), raw_name

    return False, 0.0, ""