"""
Livello 2: Fuzzy matching.
Usa rapidfuzz per similarità token-based.
Deterministico — nessuna dipendenza da LLM.
"""

from rapidfuzz import fuzz
from config import FUZZY_MATCH_THRESHOLD, FUZZY_UNCERTAIN_THRESHOLD
from matching.exact import normalize_name


def fuzzy_match(entity_norm: str, obj_name: str) -> float:
    """
    Calcola lo score di similarità fuzzy tra due nomi.
    Ritorna score 0-100.
    """
    obj_norm = normalize_name(obj_name)
    return fuzz.token_sort_ratio(entity_norm, obj_norm)


def is_strong_fuzzy(score: float) -> bool:
    """Score sufficiente per match automatico (Livello 2)."""
    return score >= FUZZY_MATCH_THRESHOLD


def is_candidate(score: float) -> bool:
    """Score sufficiente per essere candidato (Livello 3 LLM)."""
    return score >= FUZZY_UNCERTAIN_THRESHOLD
