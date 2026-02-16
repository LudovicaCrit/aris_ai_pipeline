"""
ARIS Resolver — Entry Point
============================
Orchestratore del pipeline completo:
    Word → Estrazione entità → Matching ARIS → Report

Uso:
    python3 main.py <file_word> [file_model_json]

    file_word:       il .doc/.docx del Process Owner
    file_model_json: (opzionale) il JSON del modello ARIS estratto via API
                     Se omesso, si connette direttamente all'API ARIS.

Autore: Ludovica Ignatia Di Ciaccio — IMC Group
Data: 12 febbraio 2026
"""

import sys
import json

from word_parser import read_word_file, extract_entities, summarize_entities
from resolver import resolve_all
from report import generate_html_report


def load_aris_objects_from_json(filepath: str) -> tuple[list, str]:
    """Carica oggetti ARIS da un file JSON (estratto via API)."""
    with open(filepath, 'r') as f:
        model_data = json.load(f)

    model = model_data['items'][0]

    # Estrai nome modello
    model_name = "?"
    for attr in model.get('attributes', []):
        if attr.get('apiname') == 'AT_NAME':
            model_name = attr['value']
            break

    # Estrai oggetti unici (per GUID)
    seen_guids = set()
    aris_objects = []
    for obj in model.get('modelobjects', []):
        if obj['guid'] not in seen_guids:
            seen_guids.add(obj['guid'])
            aris_objects.append(obj)

    return aris_objects, model_name


def load_aris_objects_from_api() -> tuple[list, str]:
    """Connessione live all'API ARIS (futuro)."""
    from aris_client import ARISClient
    from config import ARIS_USER, ARIS_PASSWORD

    client = ARISClient()
    if not client.login(ARIS_USER, ARIS_PASSWORD):
        print("[ERRORE] Impossibile connettersi ad ARIS.")
        sys.exit(1)

    # TODO: implementare ricerca modello e estrazione oggetti live
    print("    (Modalità live API non ancora implementata. Usa il file JSON.)")
    client.logout()
    sys.exit(0)


def main():
    print("=" * 60)
    print("  ARIS RESOLVER — v0.2 (modulare)")
    print("=" * 60)
    print()

    # --- Argomenti ---
    if len(sys.argv) < 2:
        print("Uso: python3 main.py <file_word> [file_model_json]")
        print("  file_word:       il .doc/.docx del PO")
        print("  file_model_json: (opzionale) JSON del modello ARIS")
        sys.exit(1)

    word_file = sys.argv[1]
    model_json_file = sys.argv[2] if len(sys.argv) > 2 else None

    # --- Passo 1: Leggi Word ---
    print(f"[1/4] Lettura Word: {word_file}")
    text = read_word_file(word_file)
    entities = extract_entities(text)

    summary = summarize_entities(entities)
    print(f"    Entità estratte: {len(entities)}")
    for etype, names in summary.items():
        print(f"      - {etype}: {len(names)}")

    # --- Passo 2: Carica oggetti ARIS ---
    if model_json_file:
        print(f"\n[2/4] Caricamento oggetti ARIS da file: {model_json_file}")
        aris_objects, model_name = load_aris_objects_from_json(model_json_file)
        print(f"    Oggetti ARIS unici caricati: {len(aris_objects)}")
    else:
        print(f"\n[2/4] Connessione all'API ARIS...")
        aris_objects, model_name = load_aris_objects_from_api()

    # --- Passo 3: Matching ---
    print(f"\n[3/4] Matching entità Word → ARIS")
    matches = resolve_all(entities, aris_objects)

    # --- Passo 4: Report ---
    print(f"\n[4/4] Generazione report")
    report_html = generate_html_report(matches, model_name)
    report_path = word_file.rsplit('.', 1)[0] + "_resolver_report.html"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_html)
    print(f"    Report salvato: {report_path}")

    # --- Riepilogo ---
    print(f"\n{'=' * 60}")
    print(f"  RIEPILOGO")
    print(f"{'=' * 60}")
    reuse = len([m for m in matches if m.operation == "REUSE"])
    create = len([m for m in matches if m.operation == "CREATE"])
    flag = len([m for m in matches if m.operation == "FLAG_REVIEW"])
    print(f"  Entità totali:      {len(matches)}")
    print(f"  REUSE (trovate):    {reuse}")
    print(f"  CREATE (nuove):     {create}")
    print(f"  FLAG (da rivedere): {flag}")
    print()


if __name__ == "__main__":
    main()
