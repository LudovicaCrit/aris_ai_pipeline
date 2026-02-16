"""
Template dei prompt per l'LLM.
Separati dal codice per facilitare iterazione e testing.
"""


def build_resolver_prompt(entity_name: str, entity_type: str, candidates: list) -> str:
    """
    Costruisce il prompt per il Livello 3 (risoluzione LLM).

    Il prompt vincola l'LLM a scegliere SOLO tra candidati esistenti
    o a rispondere NESSUNO. Non può inventare oggetti.
    """
    candidates_text = "\n".join(
        f"  {i+1}. \"{c['name']}\" (tipo: {c['type']}, GUID: {c['guid']}, score fuzzy: {c['score']:.0f}%)"
        for i, c in enumerate(candidates)
    )

    return f"""Sei un esperto di ARIS e mappatura processi aziendali.

Nel Word del Process Owner compare questa entità:
  Nome: "{entity_name}"
  Tipo: {entity_type}

Nel database ARIS esistono questi candidati possibili:
{candidates_text}

Quale candidato corrisponde all'entità del Word? Considera che:
- I nomi possono avere abbreviazioni, errori di battitura, o suffissi aggiuntivi
- "PUNTO-WEB" e "PUNTO-WEB (ex PUNTO NET)" sono lo stesso oggetto
- Un'entità nel Word potrebbe essere una versione abbreviata del nome ARIS
- Un errore di battitura come "Comunicazine" potrebbe essere "Comunicazione"

Rispondi SOLO con il numero del candidato (es. "1") oppure "NESSUNO" se nessun candidato corrisponde.
Non aggiungere spiegazioni."""
