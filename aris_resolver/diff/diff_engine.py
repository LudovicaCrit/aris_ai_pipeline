"""
ARIS Diff Engine — Scenario 3
==============================
Confronta le entità estratte dal Word (to-be) con il contenuto
del modello ARIS (as-is) per individuare le modifiche quando
NON sono disponibili track changes né il documento as-is.

L'as-is è il modello ARIS stesso (JSON oggi, XML domani).
Il to-be è il Word del PO.

Output: lista di diff classificate per tipo:
  - UNCHANGED: entità identica in Word e ARIS
  - MODIFIED: entità presente in entrambi ma con attributi diversi
  - ADDED: entità nel Word ma non in ARIS
  - REMOVED: entità in ARIS ma non nel Word

Autore: Ludovica Ignatia Di Ciaccio — IMC Group
Data: 17 febbraio 2026
"""

import json
import re
import sys
import os
from dataclasses import dataclass, field
from enum import Enum

# Importa dal Resolver
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'aris_resolver'))
from matching.exact import normalize_name, exact_match, containment_match
from matching.fuzzy import fuzzy_match, is_strong_fuzzy


class DiffType(Enum):
    UNCHANGED = "UNCHANGED"
    MODIFIED = "MODIFIED"
    ADDED = "ADDED"
    REMOVED = "REMOVED"


@dataclass
class EntityDiff:
    """Rappresenta una differenza tra Word e ARIS."""
    diff_type: DiffType
    entity_name: str
    entity_type: str  # activity, executor, application
    # Dati dal Word (to-be)
    word_code: str = None
    word_description: str = None
    word_raw: str = None
    # Dati da ARIS (as-is)
    aris_guid: str = None
    aris_name: str = None
    aris_description: str = None
    aris_type: str = None
    # Dettagli modifica
    changes: dict = field(default_factory=dict)
    match_score: float = 0.0
    match_method: str = ""


def extract_aris_entities(model_data: dict) -> list[dict]:
    """
    Estrae le entità dal JSON del modello ARIS (as-is).
    Restituisce una lista di dizionari con nome, guid, tipo, descrizione.
    """
    model = model_data['items'][0]
    entities = []
    seen_guids = set()

    for obj in model.get('modelobjects', []):
        guid = obj['guid']
        if guid in seen_guids:
            continue
        seen_guids.add(guid)

        # Estrai nome e descrizione dagli attributi
        name = ""
        description = ""
        obj_type = obj.get('typename', '')

        for attr in obj.get('attributes', []):
            if attr.get('apiname') == 'AT_NAME':
                name = attr.get('value', '')
            elif attr.get('apiname') == 'AT_DESC':
                description = attr.get('value', '')

        # Mappa il tipo ARIS al tipo entity
        entity_type = "unknown"
        if obj_type == "Function":
            entity_type = "activity"
        elif obj_type == "Organizational unit":
            entity_type = "executor"
        elif obj_type in ("Application system type", "Application system"):
            entity_type = "application"
        elif obj_type == "Event":
            entity_type = "event"
        elif obj_type == "Rule":
            entity_type = "rule"

        # Ignora eventi e regole per il confronto
        # (il Word tipicamente non li elenca esplicitamente)
        if entity_type in ("event", "rule"):
            continue

        entities.append({
            'name': name,
            'guid': guid,
            'type': obj_type,
            'entity_type': entity_type,
            'description': description,
            'normalized_name': normalize_name(name)
        })

    return entities


def find_best_match(word_entity, aris_entities: list[dict], threshold: float = 80.0) -> tuple:
    """
    Cerca il miglior match per un'entità Word tra le entità ARIS.
    Restituisce (aris_entity, score, method) o (None, 0, "").
    """
    word_norm = normalize_name(word_entity.name)

    # Livello 1a: match esatto
    for aris in aris_entities:
        if exact_match(word_norm, aris['normalized_name']):
            return (aris, 100.0, "Match esatto")

    # Livello 1b: contenimento
    for aris in aris_entities:
        score = containment_match(word_norm, aris['normalized_name'])
        if score:
            return (aris, score, "Match per contenimento")

    # Livello 2: fuzzy
    best_score = 0
    best_aris = None
    for aris in aris_entities:
        score = fuzzy_match(word_norm, aris['normalized_name'])
        if score > best_score:
            best_score = score
            best_aris = aris

    if best_score >= threshold:
        return (best_aris, best_score, f"Fuzzy match ({best_score:.0f}%)")

    return (None, 0, "")


def compare_descriptions(word_desc: str, aris_desc: str) -> dict:
    """
    Confronta le descrizioni Word e ARIS.
    Restituisce un dizionario con i cambiamenti rilevati.
    """
    if not word_desc and not aris_desc:
        return {}

    if not aris_desc and word_desc:
        return {"AT_DESC": {"change": "ADDED", "to_be": word_desc}}

    if aris_desc and not word_desc:
        # Il Word non ha descrizione — potrebbe essere un limite del parser
        # Non flaggare come rimossa
        return {}

    # Normalizza per confronto
    word_clean = ' '.join(word_desc.split()).strip().lower()
    aris_clean = ' '.join(aris_desc.split()).strip().lower()

    if word_clean == aris_clean:
        return {}

    return {
        "AT_DESC": {
            "change": "MODIFIED",
            "as_is": aris_desc[:200] + "..." if len(aris_desc) > 200 else aris_desc,
            "to_be": word_desc[:200] + "..." if len(word_desc) > 200 else word_desc
        }
    }


def compute_diff(word_entities, aris_entities: list[dict]) -> list[EntityDiff]:
    """
    Confronta le entità Word (to-be) con le entità ARIS (as-is).
    Restituisce la lista delle differenze.
    """
    diffs = []
    matched_aris_guids = set()

    # Per ogni entità nel Word, cerca il corrispondente in ARIS
    for we in word_entities:
        aris_match, score, method = find_best_match(we, aris_entities)

        if aris_match:
            matched_aris_guids.add(aris_match['guid'])

            # Confronta gli attributi
            changes = compare_descriptions(
                we.description if we.description else "",
                aris_match.get('description', '')
            )

            if changes:
                diff = EntityDiff(
                    diff_type=DiffType.MODIFIED,
                    entity_name=we.name,
                    entity_type=we.entity_type,
                    word_code=we.code,
                    word_description=we.description,
                    aris_guid=aris_match['guid'],
                    aris_name=aris_match['name'],
                    aris_description=aris_match.get('description', ''),
                    aris_type=aris_match['type'],
                    changes=changes,
                    match_score=score,
                    match_method=method
                )
            else:
                diff = EntityDiff(
                    diff_type=DiffType.UNCHANGED,
                    entity_name=we.name,
                    entity_type=we.entity_type,
                    word_code=we.code,
                    aris_guid=aris_match['guid'],
                    aris_name=aris_match['name'],
                    aris_type=aris_match['type'],
                    match_score=score,
                    match_method=method
                )
            diffs.append(diff)
        else:
            # Entità nel Word ma non in ARIS → nuova
            diff = EntityDiff(
                diff_type=DiffType.ADDED,
                entity_name=we.name,
                entity_type=we.entity_type,
                word_code=we.code,
                word_description=we.description
            )
            diffs.append(diff)

    # Entità in ARIS ma non nel Word → potenzialmente rimosse
    # Filtro intelligente: il Word non contiene tutti gli oggetti del modello.
    # Le process interface (riferimenti ad altri modelli, es. "2.7.1.01 Piano...")
    # non appaiono mai nel Word tabellare del PO.
    for aris in aris_entities:
        if aris['guid'] not in matched_aris_guids:
            # Filtra process interface (nomi che iniziano con codice processo)
            name = aris['name']
            is_process_interface = bool(re.match(r'^\d+\.\d+', name))

            # Filtra oggetti di tipo "unknown" (non mappati)
            is_unmapped = aris['entity_type'] == 'unknown'

            if is_process_interface or is_unmapped:
                # Non sono rimosse: il Word non le contiene per design
                continue

            diff = EntityDiff(
                diff_type=DiffType.REMOVED,
                entity_name=name,
                entity_type=aris['entity_type'],
                aris_guid=aris['guid'],
                aris_name=name,
                aris_description=aris.get('description', ''),
                aris_type=aris['type']
            )
            diffs.append(diff)

    return diffs


def diff_to_json(diffs: list[EntityDiff], model_name: str) -> dict:
    """Converte la lista di diff in un JSON strutturato."""
    from datetime import datetime

    summary = {
        "UNCHANGED": 0,
        "MODIFIED": 0,
        "ADDED": 0,
        "REMOVED": 0
    }

    items = []
    for d in diffs:
        summary[d.diff_type.value] += 1
        item = {
            "diff_type": d.diff_type.value,
            "entity_name": d.entity_name,
            "entity_type": d.entity_type,
        }
        if d.aris_guid:
            item["aris_guid"] = d.aris_guid
            item["aris_name"] = d.aris_name
            item["aris_type"] = d.aris_type
        if d.word_code:
            item["word_code"] = d.word_code
        if d.changes:
            item["changes"] = d.changes
        if d.match_score:
            item["match_score"] = d.match_score
            item["match_method"] = d.match_method

        items.append(item)

    return {
        "metadata": {
            "scenario": "3 - Word to-be vs ARIS model (no track changes)",
            "timestamp": datetime.now().isoformat(),
            "model_name": model_name,
            "summary": summary
        },
        "diffs": items
    }


def print_diff_report(diffs: list[EntityDiff]):
    """Stampa un report leggibile delle differenze."""
    icons = {
        DiffType.UNCHANGED: "⚪",
        DiffType.MODIFIED: "🔵",
        DiffType.ADDED: "🟢",
        DiffType.REMOVED: "🔴"
    }

    for d in diffs:
        icon = icons[d.diff_type]
        if d.diff_type == DiffType.UNCHANGED:
            print(f"    {icon} [{d.entity_type[:4]}] \"{d.entity_name}\" → invariata")
        elif d.diff_type == DiffType.MODIFIED:
            attrs = ", ".join(d.changes.keys())
            print(f"    {icon} [{d.entity_type[:4]}] \"{d.entity_name}\" → MODIFICATA ({attrs})")
        elif d.diff_type == DiffType.ADDED:
            print(f"    {icon} [{d.entity_type[:4]}] \"{d.entity_name}\" → NUOVA (non in ARIS)")
        elif d.diff_type == DiffType.REMOVED:
            print(f"    {icon} [{d.entity_type[:4]}] \"{d.entity_name}\" → RIMOSSA (non nel Word)")


# --- Main standalone per test ---
if __name__ == "__main__":
    from word_parser import read_word_file, extract_entities, summarize_entities

    if len(sys.argv) < 3:
        print("Uso: python3 diff_engine.py <file_word_tobe> <file_model_json>")
        sys.exit(1)

    word_file = sys.argv[1]
    model_file = sys.argv[2]

    print("=" * 60)
    print("  ARIS DIFF ENGINE — Scenario 3")
    print("  (Word to-be vs modello ARIS, senza track changes)")
    print("=" * 60)
    print()

    # Passo 1: Word
    print(f"[1/4] Lettura Word to-be: {word_file}")
    text = read_word_file(word_file)
    word_entities = extract_entities(text)
    print(f"    Entità nel Word: {len(word_entities)}")

    # Passo 2: ARIS
    print(f"\n[2/4] Caricamento modello ARIS (as-is): {model_file}")
    with open(model_file, 'r') as f:
        model_data = json.load(f)

    model = model_data['items'][0]
    model_name = "?"
    for attr in model.get('attributes', []):
        if attr.get('apiname') == 'AT_NAME':
            model_name = attr['value']
            break

    aris_entities = extract_aris_entities(model_data)
    print(f"    Entità in ARIS: {len(aris_entities)}")

    # Passo 3: Diff
    print(f"\n[3/4] Confronto Word (to-be) vs ARIS (as-is)")
    diffs = compute_diff(word_entities, aris_entities)
    print_diff_report(diffs)

    # Passo 4: Output
    print(f"\n[4/4] Generazione output")
    output = diff_to_json(diffs, model_name)

    os.makedirs("output", exist_ok=True)
    json_path = "output/diff_scenario3.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"    JSON salvato: {json_path}")

    # Riepilogo
    s = output["metadata"]["summary"]
    print(f"\n{'=' * 60}")
    print(f"  RIEPILOGO")
    print(f"{'=' * 60}")
    print(f"  ⚪ Invariate:   {s['UNCHANGED']}")
    print(f"  🔵 Modificate:  {s['MODIFIED']}")
    print(f"  🟢 Nuove:       {s['ADDED']}")
    print(f"  🔴 Rimosse:     {s['REMOVED']}")
    print()