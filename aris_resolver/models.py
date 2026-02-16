"""
Modelli dati per ARIS Resolver.
Dataclass condivise tra tutti i moduli.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WordEntity:
    """Entità estratta dal Word del PO."""
    name: str
    entity_type: str  # 'activity', 'executor', 'application', 'control'
    code: Optional[str] = None
    description: Optional[str] = None
    raw_text: Optional[str] = None


@dataclass
class ARISMatch:
    """Risultato del matching con un oggetto ARIS."""
    word_entity: WordEntity
    aris_guid: Optional[str] = None
    aris_name: Optional[str] = None
    aris_type: Optional[str] = None
    aris_type_num: Optional[int] = None
    aris_symbol: Optional[str] = None
    match_score: float = 0.0
    match_level: int = 0       # 1=esatto, 2=fuzzy, 3=LLM, 4=flag umano
    match_method: str = ""
    operation: str = "UNKNOWN"  # REUSE, CREATE, UPDATE, DELETE_OCCURRENCE
    warnings: list = field(default_factory=list)
    candidates: list = field(default_factory=list)
