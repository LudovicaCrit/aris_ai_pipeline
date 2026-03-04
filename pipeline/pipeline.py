"""
ARIS AI Pipeline — Orchestratore End-to-End v0.3
==================================================
Orchestra i due agenti indipendenti:
    1. ProcedureCheck: Word → Report (per il management)
    2. Resolver: Word + XML/JSON ARIS → JSON operazioni (per ARIS)

I due agenti lavorano sullo stesso Word.
L'XML/JSON ARIS va SOLO al Resolver.
Se un agente fallisce, l'altro continua.

NOVITÀ v0.3:
- Accetta AUTOMATICAMENTE sia JSON (API REST) che XML (export AML)
  come sorgente as-is. Detecta il formato dal file.
- Quando l'input è XML, le connessioni vengono dall'XML stesso
  (più ricche di quelle nel JSON REST).

Uso:
    # Solo Resolver (default) — JSON o XML, auto-detect
    python3 pipeline.py <file_word> <file_aris>

    # Resolver + ProcedureCheck (con Word as-is per confronto)
    python3 pipeline.py <file_word> <file_aris> --as-is <file_word_asis>

    # Resolver + Diff Engine (Scenario 3: solo to-be, niente track changes)
    python3 pipeline.py <file_word> <file_aris> --scenario3

Autore: Ludovica Ignatia Di Cianni — IMC Group
Data: 18 febbraio 2026
"""

import sys
import os
import json
import argparse
from datetime import datetime

# Path dei componenti
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RESOLVER_DIR = os.path.join(SCRIPT_DIR, '..', 'aris_resolver')
PROCCHECK_DIR = os.path.join(SCRIPT_DIR, '..', 'process_comparator_affinato')

# Aggiungi il Resolver al path
sys.path.insert(0, RESOLVER_DIR)

from word_parser import read_word_file, extract_entities, summarize_entities
from resolver import resolve_all
from report import generate_html_report
from models import ARISMatch


# ============================================================
# DETECT FORMATO INPUT (JSON o XML)
# ============================================================

def detect_format(filepath: str) -> str:
    """
    Determina se il file as-is è JSON (API REST) o XML (export AML).
    1. Per estensione (.json/.xml/.aml)
    2. Se ambiguo: sniffa i primi byte
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.json':
        return 'json'
    if ext in ('.xml', '.aml'):
        return 'xml'

    # Fallback: leggi l'inizio del file
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        head = f.read(500).strip()
    if head.startswith('{') or head.startswith('['):
        return 'json'
    if head.startswith('<?xml') or '<AML' in head or '<ObjDef' in head:
        return 'xml'

    raise ValueError(
        f"Formato non riconosciuto: '{filepath}'\n"
        f"Deve essere .json (API REST) o .xml/.aml (export ARIS)."
    )


def load_aris_model_from_xml(filepath: str) -> tuple:
    """
    Carica il modello ARIS da un file XML/AML.
    Usa xml_parser.parse_xml() che restituisce modelobjects e
    modelconnections nello STESSO formato del JSON REST.

    Returns: (model_name, aris_objects, model_data_compat)
        model_data_compat ha la stessa struttura di un JSON REST
        così compare_connections() e run_diff_engine() funzionano senza modifiche.
    """
    from xml_parser import parse_xml

    parsed = parse_xml(filepath)
    meta = parsed.get('metadata', {})

    # Nome modello: dal database o dal nome file
    model_name = meta.get('database', '')
    if not model_name:
        model_name = os.path.splitext(os.path.basename(filepath))[0]

    objects = parsed['modelobjects']
    connections = parsed.get('modelconnections', [])

    # Deduplica oggetti per GUID
    seen = set()
    unique_objects = []
    for obj in objects:
        guid = obj.get('guid', '')
        if guid and guid not in seen:
            seen.add(guid)
            unique_objects.append(obj)

    # Costruisci un dict compatibile col formato JSON REST
    # così load_aris_model() e compare_connections() funzionano identici
    model_data_compat = {
        'items': [{
            'attributes': [{'apiname': 'AT_NAME', 'value': model_name}],
            'modelobjects': unique_objects,
            'modelconnections': connections,
        }]
    }

    print(f"       Modello: {model_name}")
    print(f"       Oggetti: {len(unique_objects)}")
    print(f"       Connessioni: {len(connections)} (dall'XML)")
    if meta.get('export_date'):
        print(f"       Export: {meta['export_date']} {meta.get('export_time', '')}")

    return model_name, unique_objects, model_data_compat


def load_aris_model_from_json(model_json_file: str) -> tuple:
    """Carica il modello ARIS da JSON (API REST) e restituisce (model_name, aris_objects, model_data)."""
    with open(model_json_file, 'r') as f:
        model_data = json.load(f)

    model = model_data['items'][0]
    model_name = "?"
    for attr in model.get('attributes', []):
        if attr.get('apiname') == 'AT_NAME':
            model_name = attr['value']
            break

    seen_guids = set()
    aris_objects = []
    for obj in model.get('modelobjects', []):
        if obj['guid'] not in seen_guids:
            seen_guids.add(obj['guid'])
            aris_objects.append(obj)

    return model_name, aris_objects, model_data


def load_aris_model(filepath: str) -> tuple:
    """
    Carica il modello ARIS, auto-detect formato (JSON o XML).
    Returns: (model_name, aris_objects, model_data)

    model_data ha sempre la stessa struttura indipendentemente
    dal formato sorgente, così il resto del pipeline è agnostico.
    """
    fmt = detect_format(filepath)
    if fmt == 'json':
        return load_aris_model_from_json(filepath)
    else:
        return load_aris_model_from_xml(filepath)


def compare_connections(entities: list, model_data: dict,
                        matches: list = None) -> list:
    """
    Confronta le connessioni 'carries out' (esecutore → attività)
    tra il Word (to-be) e il modello ARIS (as-is).

    Usa i GUID risolti dal matching (R3) per cercare le connessioni
    nel modello ARIS, invece di confrontare per nome.

    Restituisce una lista di risultati:
    - OK: stesso esecutore in Word e ARIS
    - CHANGED: esecutore diverso (con GUID di entrambi)
    - NEW: attività senza GUID (non trovata dal Resolver)
    """
    model = model_data['items'][0]

    # Mappa GUID → nome oggetto
    guid_to_name = {}
    for obj in model.get('modelobjects', []):
        for attr in obj.get('attributes', []):
            if attr.get('apiname') == 'AT_NAME':
                guid_to_name[obj['guid']] = attr['value']

    # Mappa attività GUID → esecutore GUID da ARIS (connessioni 'carries out')
    # target_guid = attività, source_guid = esecutore
    aris_exec_by_guid = {}
    for conn in model.get('modelconnections', []):
        if conn.get('typename') == 'carries out':
            aris_exec_by_guid[conn['target_guid']] = conn['source_guid']

    # Mappa nome entità Word → GUID (dal matching R3)
    word_to_guid = {}
    if matches:
        for m in matches:
            if m.aris_guid and m.word_entity.entity_type in ('activity', 'executor'):
                word_to_guid[m.word_entity.name] = m.aris_guid

    # Confronta
    results = []
    for entity in entities:
        if entity.entity_type != 'activity' or not entity.executor:
            continue

        activity_guid = word_to_guid.get(entity.name)

        if not activity_guid:
            # Attività non trovata dal Resolver → nuova
            results.append({
                'status': 'NEW',
                'activity': entity.name,
                'code': entity.code,
                'word_executor': entity.executor
            })
            continue

        # Cerca connessione 'carries out' per GUID dell'attività
        aris_exec_guid = aris_exec_by_guid.get(activity_guid)
        if not aris_exec_guid:
            # Attività esiste in ARIS ma senza connessione esecutore
            results.append({
                'status': 'NEW_CONNECTION',
                'activity': entity.name,
                'activity_guid': activity_guid,
                'code': entity.code,
                'word_executor': entity.executor
            })
            continue

        aris_exec_name = guid_to_name.get(aris_exec_guid, '?')
        word_exec_guid = word_to_guid.get(entity.executor)

        # Confronta per GUID se disponibile, altrimenti per nome
        if word_exec_guid and word_exec_guid == aris_exec_guid:
            status = 'OK'
        elif aris_exec_name == entity.executor:
            status = 'OK'
        else:
            status = 'CHANGED'

        result = {
            'status': status,
            'activity': entity.name,
            'activity_guid': activity_guid,
            'code': entity.code,
            'word_executor': entity.executor,
            'aris_executor': aris_exec_name,
            'aris_executor_guid': aris_exec_guid
        }
        if word_exec_guid:
            result['word_executor_guid'] = word_exec_guid
        results.append(result)

    return results


def build_update_json(matches: list[ARISMatch], model_name: str,
                      aris_objects: list = None,
                      diff_summary: dict = None) -> dict:
    """
    Costruisce il JSON con le operazioni per ARIS.

    Confronta realmente gli attributi prima di generare UPDATE:
    solo gli oggetti con descrizione effettivamente modificata
    producono un'operazione UPDATE. Gli altri sono UNCHANGED.

    Le operazioni CREATE non vengono generate automaticamente:
    come richiesto da Reale Mutua, la creazione di nuove definizioni
    passa per il controllo umano.
    """
    operations = []
    unchanged = []
    flags_for_review = []

    # Costruisci un dizionario GUID → descrizione ARIS per confronto
    aris_desc_by_guid = {}
    if aris_objects:
        for obj in aris_objects:
            guid = obj.get('guid', '')
            desc = ''
            for attr in obj.get('attributes', []):
                if attr.get('apiname') == 'AT_DESC':
                    desc = attr.get('value', '')
                    break
            aris_desc_by_guid[guid] = desc

    for match in matches:
        entity = match.word_entity

        if match.operation == "REUSE" and match.aris_guid:
            # Confronta la descrizione Word vs ARIS
            word_desc = (entity.description or '').strip()
            aris_desc = aris_desc_by_guid.get(match.aris_guid, '').strip()

            # Normalizza per confronto
            word_clean = ' '.join(word_desc.split()).lower() if word_desc else ''
            aris_clean = ' '.join(aris_desc.split()).lower() if aris_desc else ''

            attributes_to_update = {}

            if word_desc and word_clean != aris_clean:
                # Descrizione realmente modificata → UPDATE
                attributes_to_update["AT_DESC"] = word_desc

            if attributes_to_update:
                op = {
                    "operation": "UPDATE",
                    "guid": match.aris_guid,
                    "aris_name": match.aris_name,
                    "aris_type": match.aris_type,
                    "match_level": match.match_level,
                    "match_score": match.match_score,
                    "match_method": match.match_method,
                    "word_entity": {
                        "name": entity.name,
                        "type": entity.entity_type,
                        "code": entity.code,
                        "description": entity.description
                    },
                    "attributes_to_update": attributes_to_update
                }
                operations.append(op)
            else:
                # Nessuna modifica reale → UNCHANGED
                unchanged.append({
                    "guid": match.aris_guid,
                    "aris_name": match.aris_name,
                    "word_entity": entity.name,
                    "match_level": match.match_level,
                    "match_score": match.match_score
                })

        elif match.operation == "CREATE":
            flags_for_review.append({
                "action": "REVIEW_NEW_OBJECT",
                "reason": "Oggetto non trovato in ARIS. Creazione richiede approvazione umana.",
                "word_entity": {
                    "name": entity.name,
                    "type": entity.entity_type,
                    "code": entity.code,
                    "description": entity.description
                },
                "candidates": match.candidates[:3] if match.candidates else []
            })

        elif match.operation == "FLAG_REVIEW":
            flags_for_review.append({
                "action": "REVIEW_AMBIGUOUS_MATCH",
                "reason": match.match_method,
                "word_entity": {
                    "name": entity.name,
                    "type": entity.entity_type,
                    "code": entity.code,
                    "description": entity.description
                },
                "candidates": match.candidates[:3] if match.candidates else [],
                "warnings": match.warnings
            })

    output = {
        "metadata": {
            "pipeline_version": "0.3",
            "timestamp": datetime.now().isoformat(),
            "model_name": model_name,
            "total_entities": len(matches),
            "matched_unchanged": len(unchanged),
            "auto_updates": len(operations),
            "flags_for_review": len(flags_for_review),
            "policy": "CREATE operations require human approval (Reale Mutua requirement)"
        },
        "operations": operations,
        "unchanged": unchanged,
        "review_required": flags_for_review
    }

    if diff_summary:
        output["metadata"]["diff_summary"] = diff_summary

    return output


def run_resolver(word_file: str, model_json_file: str, output_dir: str) -> dict:
    """
    Esegue il Resolver: Word → matching GUID → JSON operazioni.
    """
    print(f"\n{'─' * 50}")
    print(f"  RESOLVER")
    print(f"{'─' * 50}")

    print(f"\n  [R1] Lettura Word: {os.path.basename(word_file)}")
    text = read_word_file(word_file)
    entities = extract_entities(text)
    summary = summarize_entities(entities)
    print(f"       Entità estratte: {len(entities)}")
    for etype, names in summary.items():
        print(f"         - {etype}: {len(names)}")

    print(f"\n  [R2] Caricamento modello ARIS")
    fmt = detect_format(model_json_file)
    print(f"       Formato: {fmt.upper()}")
    model_name, aris_objects, model_data = load_aris_model(model_json_file)
    if fmt == 'json':
        print(f"       Modello: {model_name}")
        print(f"       Oggetti ARIS unici: {len(aris_objects)}")

    print(f"\n  [R3] Matching entità Word → ARIS")
    matches = resolve_all(entities, aris_objects)

    print(f"\n  [R4] Generazione JSON operazioni")
    output_json = build_update_json(matches, model_name, aris_objects=aris_objects)
    json_path = os.path.join(output_dir, "resolver_operations.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output_json, f, ensure_ascii=False, indent=2)
    print(f"       JSON → {json_path}")

    print(f"\n  [R5] Generazione report HTML")
    report_html = generate_html_report(matches, model_name)
    report_path = os.path.join(output_dir, "resolver_report.html")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_html)
    print(f"       HTML → {report_path}")

    # --- Confronto connessioni ---
    print(f"\n  [R6] Confronto connessioni (esecutore → attività)")
    conn_results = compare_connections(entities, model_data, matches=matches)
    if conn_results:
        ok = len([c for c in conn_results if c['status'] == 'OK'])
        changed = [c for c in conn_results if c['status'] == 'CHANGED']
        new = len([c for c in conn_results if c['status'] == 'NEW'])
        new_conn = len([c for c in conn_results if c['status'] == 'NEW_CONNECTION'])
        print(f"       ✅ Invariate:      {ok}")
        print(f"       🔄 Cambiate:       {len(changed)}")
        print(f"       🆕 Attività nuove: {new}")
        if new_conn:
            print(f"       🔗 Nuove connessioni: {new_conn}")
        for c in changed:
            print(f"       ⚠ [{c['activity']}]")
            print(f"         ARIS: {c['aris_executor']} ({c.get('aris_executor_guid','')[:12]}...)")
            print(f"         Word: {c['word_executor']}")
        output_json["connection_changes"] = conn_results
        # Riscrivi JSON con connessioni
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(output_json, f, ensure_ascii=False, indent=2)
    else:
        print(f"       (nessuna connessione trovata nel modello)")

    return output_json


def run_diff_engine(word_file: str, model_json_file: str, output_dir: str) -> dict:
    """
    Esegue il Diff Engine (Scenario 3): Word to-be vs modello ARIS.
    """
    sys.path.insert(0, os.path.join(RESOLVER_DIR, 'diff'))
    from diff_engine import (extract_aris_entities, compute_diff,
                             diff_to_json, print_diff_report)

    print(f"\n{'─' * 50}")
    print(f"  DIFF ENGINE (Scenario 3)")
    print(f"{'─' * 50}")

    print(f"\n  [D1] Lettura Word to-be: {os.path.basename(word_file)}")
    text = read_word_file(word_file)
    entities = extract_entities(text)
    print(f"       Entità nel Word: {len(entities)}")

    print(f"\n  [D2] Caricamento modello ARIS (as-is)")
    with open(model_json_file, 'r') as f:
        model_data = json.load(f)
    model_name = "?"
    for attr in model_data['items'][0].get('attributes', []):
        if attr.get('apiname') == 'AT_NAME':
            model_name = attr['value']
            break
    aris_entities = extract_aris_entities(model_data)
    print(f"       Entità in ARIS: {len(aris_entities)}")

    print(f"\n  [D3] Confronto Word (to-be) vs ARIS (as-is)")
    diffs = compute_diff(entities, aris_entities)
    print_diff_report(diffs)

    diff_output = diff_to_json(diffs, model_name)
    json_path = os.path.join(output_dir, "diff_scenario3.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(diff_output, f, ensure_ascii=False, indent=2)
    print(f"\n  [D4] JSON differenze → {json_path}")

    return diff_output


def run_procedure_check(word_file: str, word_asis_file: str, output_dir: str) -> bool:
    """
    Esegue ProcedureCheck: confronto Word as-is vs to-be → report.

    NOTA: placeholder. L'integrazione con ProcedureCheck verrà
    completata quando il suo formato di output JSON sarà definito.
    """
    print(f"\n{'─' * 50}")
    print(f"  PROCEDURE CHECK")
    print(f"{'─' * 50}")

    if not os.path.exists(word_asis_file):
        print(f"\n  ⚠ File as-is non trovato: {word_asis_file}")
        return False

    print(f"\n  [P1] Word to-be: {os.path.basename(word_file)}")
    print(f"  [P2] Word as-is: {os.path.basename(word_asis_file)}")
    print(f"  [P3] ⏳ Integrazione con ProcedureCheck in corso...")
    print(f"       Per ora, lanciare ProcedureCheck separatamente.")

    # TODO: Quando ProcedureCheck avrà un'interfaccia programmatica:
    # sys.path.insert(0, PROCCHECK_DIR)
    # from agent.compare_agent import run_comparison
    # result = run_comparison(word_asis_file, word_file)

    return False


def main():
    parser = argparse.ArgumentParser(
        description="ARIS AI Pipeline — Orchestratore v0.3 (JSON + XML auto-detect)"
    )
    parser.add_argument("word_file", help="Word del PO (to-be o track changes)")
    parser.add_argument("model_file", help="JSON (API REST) o XML (export AML) del modello ARIS")
    parser.add_argument("--as-is", dest="word_asis",
                        help="Word as-is per ProcedureCheck (opzionale)")
    parser.add_argument("--scenario3", action="store_true",
                        help="Attiva Diff Engine (Word vs ARIS, senza track changes)")

    args = parser.parse_args()

    print("=" * 60)
    print("  ARIS AI PIPELINE — v0.3")
    print("  (JSON + XML auto-detect)")
    print("=" * 60)

    has_asis = args.word_asis is not None

    if has_asis:
        print(f"  Modalità: Word as-is + to-be → ProcedureCheck + Resolver")
    elif args.scenario3:
        print(f"  Modalità: Scenario 3 → Diff Engine + Resolver")
    else:
        print(f"  Modalità: Word (track changes) → Resolver")

    print(f"  Word: {os.path.basename(args.word_file)}")
    print(f"  ARIS: {os.path.basename(args.model_file)}")
    if has_asis:
        print(f"  As-is: {os.path.basename(args.word_asis)}")

    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(output_dir, exist_ok=True)

    # ═══════════════════════════════════════════════════
    # AGENTE 1: ProcedureCheck (report per management)
    # Riceve: Word
    # Produce: Report Word
    # ═══════════════════════════════════════════════════
    if has_asis:
        try:
            run_procedure_check(args.word_file, args.word_asis, output_dir)
        except Exception as e:
            print(f"\n  ⚠ ProcedureCheck fallito: {e}")
            print(f"  ⚠ Il Resolver continua indipendentemente.")

    # ═══════════════════════════════════════════════════
    # AGENTE 2a: Diff Engine (Scenario 3, se richiesto)
    # Riceve: Word + JSON/XML ARIS
    # Produce: JSON differenze
    # ═══════════════════════════════════════════════════
    diff_output = None
    if args.scenario3:
        try:
            diff_output = run_diff_engine(args.word_file, args.model_file, output_dir)
        except Exception as e:
            print(f"\n  ⚠ Diff Engine fallito: {e}")

    # ═══════════════════════════════════════════════════
    # AGENTE 2b: Resolver (operazioni ARIS)
    # Riceve: Word + JSON/XML ARIS
    # Produce: JSON operazioni UPDATE/REVIEW
    # ═══════════════════════════════════════════════════
    try:
        resolver_output = run_resolver(args.word_file, args.model_file, output_dir)
    except Exception as e:
        print(f"\n  ❌ Resolver fallito: {e}")
        sys.exit(1)

    # ═══════════════════════════════════════════════════
    # RIEPILOGO
    # ═══════════════════════════════════════════════════
    meta = resolver_output["metadata"]
    print(f"\n{'=' * 60}")
    print(f"  RIEPILOGO PIPELINE v0.3")
    print(f"{'=' * 60}")
    print(f"  Entità totali:         {meta['total_entities']}")
    print(f"  GUID trovati, invariati: {meta['matched_unchanged']}")
    print(f"  UPDATE reali:          {meta['auto_updates']}")
    print(f"  Da rivedere (umano):   {meta['flags_for_review']}")

    if diff_output:
        ds = diff_output["metadata"]["summary"]
        print(f"\n  Diff Engine (Scenario 3):")
        print(f"    ⚪ Invariate:   {ds['UNCHANGED']}")
        print(f"    🔵 Modificate:  {ds['MODIFIED']}")
        print(f"    🟢 Nuove:       {ds['ADDED']}")
        print(f"    🔴 Rimosse:     {ds['REMOVED']}")

    conn_changes = resolver_output.get("connection_changes", [])
    if conn_changes:
        c_ok = len([c for c in conn_changes if c['status'] == 'OK'])
        c_changed = len([c for c in conn_changes if c['status'] == 'CHANGED'])
        c_new = len([c for c in conn_changes if c['status'] == 'NEW'])
        print(f"\n  Connessioni (esecutore → attività):")
        print(f"    ✅ Invariate:   {c_ok}")
        print(f"    🔄 Cambiate:    {c_changed}")
        print(f"    🆕 Nuove:       {c_new}")

    print(f"\n  Output in: {output_dir}/")
    print()


if __name__ == "__main__":
    main()