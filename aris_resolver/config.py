"""
Configurazione centralizzata per ARIS Resolver.
Tutte le soglie, credenziali e parametri stanno qui.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# ARIS API
# ============================================================
ARIS_BASE_URL = os.getenv("ARIS_BASE_URL", "https://37.60.254.72")
ARIS_DB_NAME = os.getenv("ARIS_DB_NAME", "TEST IA")
ARIS_TENANT = os.getenv("ARIS_TENANT", "default")
ARIS_USER = os.getenv("ARIS_USER", "system")
ARIS_PASSWORD = os.getenv("ARIS_PASSWORD", "manager")

# ============================================================
# LLM
# ============================================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# ============================================================
# SOGLIE DI MATCHING
# ============================================================
EXACT_MATCH_THRESHOLD = 100    # Score per match perfetto
FUZZY_MATCH_THRESHOLD = 80     # Score minimo per fuzzy match accettabile
FUZZY_UNCERTAIN_THRESHOLD = 60 # Sotto questo: nessun candidato
CONTAINMENT_MIN_LENGTH = 4     # Lunghezza minima per match per contenimento
CONTAINMENT_MIN_RATIO = 0.5    # Rapporto minimo corto/lungo per contenimento
