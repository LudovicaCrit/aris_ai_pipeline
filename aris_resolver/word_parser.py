"""
Parser per i Word dei Process Owner.
Estrae entità (attività, esecutori, applicativi, controlli) dal testo
e preserva le relazioni tra di loro.

Ogni attività porta con sé il nome dell'esecutore e dell'applicativo
estratti dallo stesso blocco tabellare. Questo permette al Resolver
di confrontare le connessioni Word (to-be) con quelle ARIS (as-is).

Supporta:
- File .doc (RTF) tramite striprtf
- File .docx tramite python-docx
"""

import re
from models import WordEntity


def read_word_file(filepath: str) -> str:
    """Legge un file Word e restituisce il testo."""
    if filepath.endswith('.doc'):
        from striprtf.striprtf import rtf_to_text
        with open(filepath, 'r', encoding='cp1252', errors='replace') as f:
            return rtf_to_text(f.read())
    elif filepath.endswith('.docx'):
        import docx
        doc = docx.Document(filepath)
        return "\n".join(p.text for p in doc.paragraphs)
    else:
        raise ValueError(f"Formato non supportato: {filepath}")


def extract_entities(text: str) -> list[WordEntity]:
    """
    Estrae entità dal testo del Word.

    Parsa la struttura tabellare dei Word di Reale Mutua:
    - Righe con codice attività (es. '010|TITOLO...')
    - Campi ESECUTORE, APPLICATIVO INFORMATICO

    Ogni attività conserva il legame con il proprio esecutore e applicativo.
    Gli esecutori e gli applicativi vengono anche aggiunti come entità
    separate (per il matching GUID), ma il legame resta sull'attività.
    """
    entities = []
    executors_seen = set()
    apps_seen = set()

    # Split per blocchi attività
    blocks = re.split(r'\n(\d{2,4})\|', text)

    for i in range(1, len(blocks), 2):
        code = blocks[i]
        content = blocks[i + 1] if i + 1 < len(blocks) else ""

        # Estrai titolo attività
        title_match = re.search(r'TITOLO\s*\n(.+?)(?:\nDESCRIZIONE|\n)', content)
        if not title_match:
            continue

        title = title_match.group(1).strip()

        # Estrai descrizione
        desc_match = re.search(
            r'DESCRIZIONE\s*\n(.+?)(?:\nALTRO STRUMENTO|\nGESTIONE ANOMALIA)',
            content, re.DOTALL
        )
        desc = desc_match.group(1).strip() if desc_match else None

        # Estrai esecutore (nome)
        executor_name = None
        exec_match = re.search(r'ESECUTORE\s*\n(.+)', content)
        if exec_match:
            executor_raw = exec_match.group(1).strip()
            if executor_raw and executor_raw != '-':
                executor_name = executor_raw

        # Estrai applicativo (nome)
        app_name = None
        app_match = re.search(r'APPLICATIVO INFORMATICO\s*\n(.+)', content)
        if app_match:
            app_raw = app_match.group(1).strip()
            if app_raw and app_raw != '-':
                app_name = app_raw

        # Aggiungi l'attività CON le relazioni
        entities.append(WordEntity(
            name=title,
            entity_type='activity',
            code=code,
            description=desc,
            executor=executor_name,
            application=app_name
        ))

        # Aggiungi esecutore come entità separata (per matching GUID)
        if executor_name and executor_name not in executors_seen:
            executors_seen.add(executor_name)
            entities.append(WordEntity(
                name=executor_name,
                entity_type='executor'
            ))

        # Aggiungi applicativo come entità separata (per matching GUID)
        if app_name and app_name not in apps_seen:
            apps_seen.add(app_name)
            entities.append(WordEntity(
                name=app_name,
                entity_type='application'
            ))

    return entities


def summarize_entities(entities: list[WordEntity]) -> dict:
    """Produce un riepilogo delle entità estratte."""
    summary = {}
    for e in entities:
        summary.setdefault(e.entity_type, []).append(e.name)
    return summary


def summarize_relationships(entities: list[WordEntity]) -> list[dict]:
    """
    Produce un riepilogo delle relazioni estratte.
    Restituisce una lista di dizionari con attività, esecutore, applicativo.
    Utile per debug e per il futuro confronto con le connessioni ARIS.
    """
    relationships = []
    for e in entities:
        if e.entity_type == 'activity' and (e.executor or e.application):
            rel = {
                'activity': e.name,
                'code': e.code,
            }
            if e.executor:
                rel['executor'] = e.executor
            if e.application:
                rel['application'] = e.application
            relationships.append(rel)
    return relationships