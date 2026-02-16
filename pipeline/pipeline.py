"""
ARIS AI Pipeline — Orchestratore End-to-End v0.1
==================================================
Collega i componenti esistenti in un flusso unico:
    Word del PO → Estrazione entità → Matching GUID → JSON operazioni

NON modifica ProcedureCheck né il Resolver.
Importa i moduli dal Resolver e li orchestra.

Uso:
    python3 pipeline.py <file_word> <file_model_json>

Output:
    - JSON con operazioni UPDATE pronte per ARIS
    - Report HTML del matching (dal Resolver)

Autore: Ludovica Ignatia Di Ciaccio — IMC Group
Data: 16 febbraio 2026
"""

import sys
import os
import json
from datetime import datetime

# Aggiungi il path del Resolver per importare i moduli
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'aris_resolver'))

from word_parser import read_word_file, extract_entities, summarize_entities
from resolver import resolve_all
from report import generate_html_report
from models import ARISMatch


def build_update_json(matches: list[ARISMatch], model_name: str) -> dict:
    """
    Costruisce il JSON con le operazioni per ARIS.

    Per ora genera solo operazioni UPDATE (aggiornamento attributi)
    e FLAG per oggetti nuovi che richiedono revisione umana.

    Le operazioni CREATE non vengono generate automaticamente:
    come richiesto da Reale Mutua, la creazione di nuove definizioni
    passa per il controllo umano.
    """
    operations = []
    flags_for_review = []

    for match in matches:
        entity = match.word_entity

        if match.operation == "REUSE" and match.aris_guid:
            # Oggetto trovato → operazione UPDATE
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
                "attributes_to_update": {}
            }

            # Se il Word ha una descrizione, preparala per l'update
            if entity.description:
                op["attributes_to_update"]["AT_DESC"] = entity.description

            operations.append(op)

        elif match.operation == "CREATE":
            # Oggetto nuovo → NON creare automaticamente, flagga
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
            # Match incerto → flagga per revisione
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

    # Costruisci il JSON finale
    output = {
        "metadata": {
            "pipeline_version": "0.1",
            "timestamp": datetime.now().isoformat(),
            "model_name": model_name,
            "total_entities": len(matches),
            "auto_updates": len(operations),
            "flags_for_review": len(flags_for_review),
            "policy": "CREATE operations require human approval (Reale Mutua requirement)"
        },
        "operations": operations,
        "review_required": flags_for_review
    }

    return output


def main():
    print("=" * 60)
    print("  ARIS AI PIPELINE — v0.1")
    print("=" * 60)
    print()

    # --- Argomenti ---
    if len(sys.argv) < 3:
        print("Uso: python3 pipeline.py <file_word> <file_model_json>")
        sys.exit(1)

    word_file = sys.argv[1]
    model_json_file = sys.argv[2]

    # --- Passo 1: Leggi Word ---
    print(f"[1/5] Lettura Word: {word_file}")
    text = read_word_file(word_file)
    entities = extract_entities(text)

    summary = summarize_entities(entities)
    print(f"    Entità estratte: {len(entities)}")
    for etype, names in summary.items():
        print(f"      - {etype}: {len(names)}")

    # --- Passo 2: Carica oggetti ARIS ---
    print(f"\n[2/5] Caricamento oggetti ARIS da: {model_json_file}")
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
    print(f"    Oggetti ARIS unici: {len(aris_objects)}")

    # --- Passo 3: Matching ---
    print(f"\n[3/5] Matching entità Word → ARIS")
    matches = resolve_all(entities, aris_objects)

    # --- Passo 4: Genera JSON operazioni ---
    print(f"\n[4/5] Generazione JSON operazioni")
    output_json = build_update_json(matches, model_name)

    json_path = os.path.join("output", "pipeline_output.json")
    os.makedirs("output", exist_ok=True)
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output_json, f, ensure_ascii=False, indent=2)
    print(f"    JSON salvato: {json_path}")

    # --- Passo 5: Report HTML ---
    print(f"\n[5/5] Generazione report HTML")
    report_html = generate_html_report(matches, model_name)
    report_path = os.path.join("output", "pipeline_report.html")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_html)
    print(f"    Report salvato: {report_path}")

    # --- Riepilogo ---
    meta = output_json["metadata"]
    print(f"\n{'=' * 60}")
    print(f"  RIEPILOGO PIPELINE")
    print(f"{'=' * 60}")
    print(f"  Entità totali:         {meta['total_entities']}")
    print(f"  UPDATE automatici:     {meta['auto_updates']}")
    print(f"  Da rivedere (umano):   {meta['flags_for_review']}")
    print(f"  Policy:                {meta['policy']}")
    print()
    print(f"  Output:")
    print(f"    JSON → {json_path}")
    print(f"    HTML → {report_path}")
    print()


if __name__ == "__main__":
    main()
