"""
Livello 1: Match esatto e per contenimento.
Puro Python — deterministico, nessuna dipendenza esterna.
"""

import re
from config import CONTAINMENT_MIN_LENGTH, CONTAINMENT_MIN_RATIO


def normalize_name(name: str) -> str:
    """Normalizza un nome per il confronto."""
    name = name.lower().strip()
    name = re.sub(r'\s+', ' ', name)
    name = re.sub(r'[^\w\s]', '', name)
    return name


def exact_match(entity_norm: str, obj_name: str) -> float | None:
    """
    Match esatto: nomi normalizzati identici.
    Ritorna score 100.0 se match, None altrimenti.
    """
    obj_norm = normalize_name(obj_name)
    if entity_norm == obj_norm:
        return 100.0
    return None


def containment_match(entity_norm: str, obj_name: str) -> float | None:
    """
    Match per contenimento: un nome è contenuto nell'altro.
    Ritorna score 95.0 se match con criteri di sicurezza, None altrimenti.
    """
    obj_norm = normalize_name(obj_name)

    if entity_norm in obj_norm or obj_norm in entity_norm:
        shorter = min(len(entity_norm), len(obj_norm))
        longer = max(len(entity_norm), len(obj_norm))
        if shorter >= CONTAINMENT_MIN_LENGTH and shorter / longer >= CONTAINMENT_MIN_RATIO:
            return 95.0

    return None
