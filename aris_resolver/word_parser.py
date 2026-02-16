"""
Parser per i Word dei Process Owner.
Estrae entità (attività, esecutori, applicativi, controlli) dal testo.
Puro Python — nessuna dipendenza da LLM.

Supporta:
- File .doc (RTF) tramite striprtf
- File .docx tramite python-docx (futuro)
- Word con track changes (estrazione modifiche — futuro)
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
        if title_match:
            title = title_match.group(1).strip()
            desc_match = re.search(
                r'DESCRIZIONE\s*\n(.+?)(?:\nALTRO STRUMENTO|\nGESTIONE ANOMALIA)',
                content, re.DOTALL
            )
            desc = desc_match.group(1).strip() if desc_match else None

            entities.append(WordEntity(
                name=title,
                entity_type='activity',
                code=code,
                description=desc
            ))

        # Estrai esecutore
        exec_match = re.search(r'ESECUTORE\s*\n(.+)', content)
        if exec_match:
            executor = exec_match.group(1).strip()
            if executor and executor != '-' and executor not in executors_seen:
                executors_seen.add(executor)
                entities.append(WordEntity(
                    name=executor,
                    entity_type='executor'
                ))

        # Estrai applicativo
        app_match = re.search(r'APPLICATIVO INFORMATICO\s*\n(.+)', content)
        if app_match:
            app = app_match.group(1).strip()
            if app and app != '-' and app not in apps_seen:
                apps_seen.add(app)
                entities.append(WordEntity(
                    name=app,
                    entity_type='application'
                ))

    return entities


def summarize_entities(entities: list[WordEntity]) -> dict:
    """Produce un riepilogo delle entità estratte."""
    summary = {}
    for e in entities:
        summary.setdefault(e.entity_type, []).append(e.name)
    return summary
