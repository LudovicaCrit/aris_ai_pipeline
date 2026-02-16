"""
Livello 3: Risoluzione tramite LLM.
UNICO modulo che dipende dall'LLM.

L'LLM NON inventa oggetti — sceglie SOLO tra candidati esistenti
o risponde NESSUNO.
"""

import google.generativeai as genai
from config import GEMINI_API_KEY, GEMINI_MODEL
from prompts.resolver_prompt import build_resolver_prompt

# Configurazione LLM
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


def llm_resolve(entity_name: str, entity_type: str, candidates: list) -> dict | None:
    """
    Chiede all'LLM di scegliere tra candidati esistenti.

    Args:
        entity_name: nome dell'entità dal Word
        entity_type: tipo dell'entità (activity, executor, application)
        candidates: lista di dict con 'name', 'type', 'guid', 'score'

    Returns:
        Il candidato scelto (dict) o None se nessun match
    """
    if not candidates or not GEMINI_API_KEY:
        return None

    prompt = build_resolver_prompt(entity_name, entity_type, candidates)

    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(prompt)
        answer = response.text.strip()

        if answer.upper() == "NESSUNO":
            return None

        # Estrai il numero dalla risposta
        num = int(''.join(c for c in answer if c.isdigit()))
        if 1 <= num <= len(candidates):
            return candidates[num - 1]

    except Exception as e:
        print(f"    [LLM WARN] Errore Livello 3: {e}")

    return None
