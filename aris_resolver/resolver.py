"""
Orchestratore del Resolver.
Chiama i livelli di matching in cascata: esatto → fuzzy → LLM → flag umano.
Non sa come funzionano i livelli internamente — li chiama e basta.
"""

from models import WordEntity, ARISMatch
from matching.exact import normalize_name, exact_match, containment_match
from matching.fuzzy import fuzzy_match, is_strong_fuzzy, is_candidate
from matching.llm_resolver import llm_resolve


def resolve_entity(entity: WordEntity, aris_objects: list) -> ARISMatch:
    """
    Cerca il miglior match per un'entità del Word tra gli oggetti ARIS.

    Cascata:
        Livello 1a: Match esatto (nome normalizzato identico)
        Livello 1b: Match per contenimento (un nome dentro l'altro)
        Livello 2:  Fuzzy matching (similarità > soglia)
        Livello 3:  LLM sceglie tra candidati incerti
        Livello 4:  Nessun match → flag per revisione umana o CREATE
    """
    match = ARISMatch(word_entity=entity)
    entity_norm = normalize_name(entity.name)

    best_score = 0
    best_obj = None
    candidates = []

    for obj in aris_objects:
        # Estrai nome dell'oggetto ARIS
        obj_name = _get_obj_name(obj)
        if not obj_name:
            continue

        # --- Livello 1a: Match esatto ---
        score = exact_match(entity_norm, obj_name)
        if score:
            _fill_match(match, obj, obj_name, score, level=1,
                        method="Match esatto (nome normalizzato)")
            return match

        # --- Livello 1b: Match per contenimento ---
        score = containment_match(entity_norm, obj_name)
        if score:
            _fill_match(match, obj, obj_name, score, level=1,
                        method="Match per contenimento (nome incluso)")
            return match

        # --- Livello 2: Fuzzy matching (raccoglie candidati) ---
        score = fuzzy_match(entity_norm, obj_name)
        if score > best_score:
            best_score = score
            best_obj = obj

        if is_candidate(score):
            candidates.append({
                "guid": obj["guid"],
                "name": obj_name,
                "type": obj.get("typename", ""),
                "score": score
            })

    # Valuta il miglior fuzzy match
    if best_obj and is_strong_fuzzy(best_score):
        obj_name = _get_obj_name(best_obj)
        _fill_match(match, best_obj, obj_name, best_score, level=2,
                    method=f"Fuzzy match (score: {best_score:.1f})")
        match.candidates = sorted(candidates, key=lambda x: x["score"], reverse=True)[:5]
        return match

    # --- Livello 3: LLM ---
    if candidates:
        sorted_candidates = sorted(candidates, key=lambda x: x["score"], reverse=True)[:5]
        llm_choice = llm_resolve(entity.name, entity.entity_type, sorted_candidates)

        if llm_choice:
            match.aris_guid = llm_choice["guid"]
            match.aris_name = llm_choice["name"]
            match.aris_type = llm_choice.get("type", "")
            match.match_score = llm_choice["score"]
            match.match_level = 3
            match.match_method = f"LLM ha scelto tra {len(sorted_candidates)} candidati"
            match.operation = "REUSE"
            match.candidates = sorted_candidates
            return match
        else:
            # LLM dice NESSUNO → flag umano
            match.match_score = best_score
            match.match_level = 4
            match.match_method = f"LLM: nessun match tra {len(sorted_candidates)} candidati"
            match.operation = "FLAG_REVIEW"
            match.candidates = sorted_candidates
            match.warnings.append(
                f"LLM non ha trovato corrispondenze tra {len(sorted_candidates)} candidati."
            )
            return match

    # --- Livello 4: Nessun candidato → probabile nuovo oggetto ---
    match.match_score = 0
    match.match_level = 4
    match.match_method = "Nessun candidato trovato"
    match.operation = "CREATE"
    match.warnings.append("Oggetto non trovato nel database. Potrebbe essere nuovo.")
    return match


def resolve_all(entities: list[WordEntity], aris_objects: list) -> list[ARISMatch]:
    """Risolve tutte le entità e stampa il progresso."""
    matches = []
    level_emoji = {1: "✅", 2: "🔶", 3: "🤖", 4: "❌"}

    for entity in entities:
        match = resolve_entity(entity, aris_objects)
        matches.append(match)

        emoji = level_emoji.get(match.match_level, "?")
        print(f"    {emoji} [{entity.entity_type[:4]}] \"{entity.name}\" → ", end="")
        if match.aris_guid:
            print(f"MATCH L{match.match_level} ({match.match_score:.0f}%) → \"{match.aris_name}\"")
        else:
            print(f"NESSUN MATCH → {match.operation}")

    return matches


# --- Utilità interne ---

def _get_obj_name(obj: dict) -> str:
    """Estrae il nome AT_NAME da un oggetto ARIS."""
    for attr in obj.get("attributes", []):
        if attr.get("apiname") == "AT_NAME":
            return attr["value"]
    return ""


def _fill_match(match: ARISMatch, obj: dict, obj_name: str,
                score: float, level: int, method: str):
    """Compila un ARISMatch con i dati dell'oggetto trovato."""
    match.aris_guid = obj["guid"]
    match.aris_name = obj_name
    match.aris_type = obj.get("typename", "")
    match.aris_type_num = obj.get("type")
    match.aris_symbol = obj.get("symbolname", "")
    match.match_score = score
    match.match_level = level
    match.match_method = method
    match.operation = "REUSE"
