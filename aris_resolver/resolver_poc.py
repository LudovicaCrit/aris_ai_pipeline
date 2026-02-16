"""
ARIS Resolver - Prototipo v0.1
================================
Primo script che mette in comunicazione il Word del PO con il database ARIS via API REST.

Cosa fa:
1. Estrae le entità dal Word (attività, esecutori, applicativi)
2. Per ciascuna, cerca il match nel database ARIS via API REST
3. Produce un report di matching con GUID trovati e livello di confidenza

Questo è il Livello 1 + Livello 2 della cascata (match esatto + fuzzy).
I Livelli 3 (LLM) e 4 (flag umano) verranno aggiunti successivamente.

Requisiti:
- Python 3.10+
- pip install requests striprtf rapidfuzz
- Accesso all'API REST ARIS (token UMC valido)

Autore: Ludovica Ignatia Di Ciaccio - IMC Group
Data: 12 febbraio 2026
"""

import json
import re
import requests
import urllib3
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional
from rapidfuzz import fuzz
import os
from dotenv import load_dotenv
import google.generativeai as genai

# Carica la chiave API
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Disabilita warning SSL per certificati self-signed
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ============================================================
# CONFIGURAZIONE
# ============================================================

ARIS_BASE_URL = "https://37.60.254.72"
ARIS_DB_NAME = "TEST IA"
ARIS_TENANT = "default"
# NOTA: username e password NON vanno hardcodati in produzione.
# Per il POC usiamo variabili che verranno passate da riga di comando.
ARIS_USER = "system"
ARIS_PASSWORD = "manager"

# Soglie di matching
EXACT_MATCH_THRESHOLD = 100   # Score per match perfetto (dopo normalizzazione)
FUZZY_MATCH_THRESHOLD = 80    # Score minimo per fuzzy match accettabile
FUZZY_UNCERTAIN_THRESHOLD = 60  # Sotto questo: flag per revisione umana


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class WordEntity:
    """Entità estratta dal Word del PO."""
    name: str
    entity_type: str  # 'activity', 'executor', 'application', 'control'
    code: Optional[str] = None  # Codice attività (es. '010', '020')
    description: Optional[str] = None
    raw_text: Optional[str] = None


@dataclass
class ARISMatch:
    """Risultato del matching con un oggetto ARIS."""
    word_entity: WordEntity
    aris_guid: Optional[str] = None
    aris_name: Optional[str] = None
    aris_type: Optional[str] = None
    aris_type_num: Optional[int] = None
    aris_symbol: Optional[str] = None
    match_score: float = 0.0
    match_level: int = 0  # 1=esatto, 2=fuzzy, 3=LLM, 4=flag umano
    match_method: str = ""
    operation: str = "UNKNOWN"  # REUSE, CREATE, UPDATE, DELETE_OCCURRENCE
    warnings: list = field(default_factory=list)
    candidates: list = field(default_factory=list)  # Per livello 2-3: candidati multipli


# ============================================================
# ARIS API CLIENT
# ============================================================

class ARISClient:
    """Client per l'API REST di ARIS Repository."""

    def __init__(self, base_url: str, db_name: str, tenant: str = "default"):
        self.base_url = base_url.rstrip("/")
        self.db_name = db_name
        self.tenant = tenant
        self.token = None
        self.session = requests.Session()
        self.session.verify = False  # Self-signed cert

    def login(self, username: str, password: str) -> bool:
        """Ottiene un token UMC per l'autenticazione API."""
        url = f"{self.base_url}/umc/api/v2/tokens"
        params = {
            "tenant": self.tenant,
            "name": username,
            "password": password
        }
        try:
            resp = self.session.post(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            self.token = data["token"]
            print(f"[LOGIN] Autenticazione riuscita. Token ottenuto.")
            return True
        except Exception as e:
            print(f"[ERRORE] Login fallito: {e}")
            return False

    def logout(self):
        """Rilascia il token UMC e la licenza ARIS."""
        if self.token:
            url = f"{self.base_url}/umc/api/tokens/{self.token}"
            try:
                self.session.delete(url)
                print("[LOGOUT] Token rilasciato.")
            except Exception:
                pass
            self.token = None

    def _get(self, endpoint: str, params: dict = None) -> dict:
        """Chiamata GET generica all'API ARIS."""
        if params is None:
            params = {}
        params["umcsession"] = self.token
        url = f"{self.base_url}/abs/api/{endpoint}"
        resp = self.session.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    def find_objects(self, name: str, object_types: list = None, language: str = "it") -> list:
        """
        Cerca oggetti nel database per nome.
        Usa l'endpoint /find con filtro sul nome.
        """
        db_encoded = self.db_name.replace(" ", "%20")
        params = {
            "kind": "OBJECT",
            "language": language,
            "attrfilter": f"AT_NAME={name}",
            "attributes": "all",
            "pagesize": 50
        }
        if object_types:
            params["typefilter"] = ",".join(str(t) for t in object_types)

        try:
            result = self._get(f"databases/{db_encoded}/find", params)
            return result.get("items", [])
        except Exception as e:
            print(f"  [WARN] Ricerca fallita per '{name}': {e}")
            return []

    def get_model_content(self, model_guid: str, language: str = "it") -> dict:
        """Recupera il contenuto completo di un modello (oggetti + connessioni)."""
        db_encoded = self.db_name.replace(" ", "%20")
        params = {
            "withcontent": "true",
            "language": language,
            "attributes": "all"
        }
        result = self._get(f"models/{db_encoded}/{model_guid}", params)
        if result.get("items"):
            return result["items"][0]
        return {}


# ============================================================
# WORD PARSER (semplificato per il POC)
# ============================================================

def extract_entities_from_word_text(text: str) -> list[WordEntity]:
    """
    Estrae entità dal testo del Word.

    Per il POC, parsa la struttura tabellare del Word di Reale Mutua:
    - Righe con codice attività (es. '010|TITOLO...')
    - Campi ESECUTORE, APPLICATIVO INFORMATICO
    """
    entities = []
    executors_seen = set()
    apps_seen = set()

    # Split per blocchi attività (separati da codice numerico)
    blocks = re.split(r'\n(\d{2,4})\|', text)

    for i in range(1, len(blocks), 2):
        code = blocks[i]
        content = blocks[i + 1] if i + 1 < len(blocks) else ""

        # Estrai titolo attività
        title_match = re.search(r'TITOLO\s*\n(.+?)(?:\nDESCRIZIONE|\n)', content)
        if title_match:
            title = title_match.group(1).strip()
            desc_match = re.search(r'DESCRIZIONE\s*\n(.+?)(?:\nALTRO STRUMENTO|\nGESTIONE ANOMALIA)', content, re.DOTALL)
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


# ============================================================
# MATCHING ENGINE (Cascata Livelli 1-2)
# ============================================================

def normalize_name(name: str) -> str:
    """Normalizza un nome per il confronto: lowercase, strip, rimuovi punteggiatura extra."""
    name = name.lower().strip()
    name = re.sub(r'\s+', ' ', name)  # Spazi multipli → singolo
    name = re.sub(r'[^\w\s]', '', name)  # Rimuovi punteggiatura
    return name

def llm_resolve(entity_name: str, entity_type: str, candidates: list) -> dict | None:
    """
    Livello 3: chiede all'LLM di scegliere tra candidati esistenti.
    L'LLM NON può inventare oggetti — sceglie solo tra quelli proposti o dice NESSUNO.
    """
    if not candidates:
        return None

    candidates_text = "\n".join(
        f"  {i+1}. \"{c['name']}\" (tipo: {c['type']}, GUID: {c['guid']}, score fuzzy: {c['score']:.0f}%)"
        for i, c in enumerate(candidates)
    )

    prompt = f"""Sei un esperto di ARIS e mappatura processi aziendali.

Nel Word del Process Owner compare questa entità:
  Nome: "{entity_name}"
  Tipo: {entity_type}

Nel database ARIS esistono questi candidati possibili:
{candidates_text}

Quale candidato corrisponde all'entità del Word? Considera che:
- I nomi possono avere abbreviazioni, errori di battitura, o suffissi aggiuntivi
- "PUNTO-WEB" e "PUNTO-WEB (ex PUNTO NET)" sono lo stesso oggetto
- Un'entità nel Word potrebbe essere una versione abbreviata del nome ARIS

Rispondi SOLO con il numero del candidato (es. "1") oppure "NESSUNO" se nessun candidato corrisponde.
Non aggiungere spiegazioni."""

    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)
        answer = response.text.strip()

        if answer == "NESSUNO":
            return None

        # Estrai il numero
        num = int(''.join(c for c in answer if c.isdigit()))
        if 1 <= num <= len(candidates):
            return candidates[num - 1]
    except Exception as e:
        print(f"    [LLM WARN] Errore Livello 3: {e}")

    return None


def match_entity_against_aris(entity: WordEntity, aris_objects: list) -> ARISMatch:
    """
    Cerca il miglior match per un'entità del Word tra gli oggetti ARIS.

    Livello 1: Match esatto (nome normalizzato identico)
    Livello 2: Fuzzy matching (similarità > soglia)
    Livello 4: Nessun match → flag per revisione umana
    """
    match = ARISMatch(word_entity=entity)
    entity_norm = normalize_name(entity.name)

    best_score = 0
    best_obj = None
    candidates = []

    for obj in aris_objects:
        obj_name = ""
        for attr in obj.get("attributes", []):
            if attr.get("apiname") == "AT_NAME":
                obj_name = attr["value"]
                break

        if not obj_name:
            continue

        obj_norm = normalize_name(obj_name)

        # Livello 1: Match esatto
        if entity_norm == obj_norm:
            match.aris_guid = obj["guid"]
            match.aris_name = obj_name
            match.aris_type = obj.get("typename", "")
            match.aris_type_num = obj.get("type")
            match.aris_symbol = obj.get("symbolname", "")
            match.match_score = 100.0
            match.match_level = 1
            match.match_method = "Match esatto (nome normalizzato)"
            match.operation = "REUSE"
            return match

        # Livello 1b: Match per contenimento (nome Word contenuto nel nome ARIS)
        if entity_norm in obj_norm or obj_norm in entity_norm:
            shorter = min(len(entity_norm), len(obj_norm))
            longer = max(len(entity_norm), len(obj_norm))
            if shorter >= 4 and shorter / longer >= 0.5:  # Almeno 50% di copertura
                match.aris_guid = obj["guid"]
                match.aris_name = obj_name
                match.aris_type = obj.get("typename", "")
                match.aris_type_num = obj.get("type")
                match.aris_symbol = obj.get("symbolname", "")
                match.match_score = 95.0
                match.match_level = 1
                match.match_method = "Match per contenimento (nome incluso)"
                match.operation = "REUSE"
                return match

        # Livello 2: Fuzzy matching
        score = fuzz.token_sort_ratio(entity_norm, obj_norm)
        if score > best_score:
            best_score = score
            best_obj = obj

        if score >= FUZZY_UNCERTAIN_THRESHOLD:
            candidates.append({
                "guid": obj["guid"],
                "name": obj_name,
                "type": obj.get("typename", ""),
                "score": score
            })

    # Valuta il miglior fuzzy match
    if best_obj and best_score >= FUZZY_MATCH_THRESHOLD:
        obj_name = ""
        for attr in best_obj.get("attributes", []):
            if attr.get("apiname") == "AT_NAME":
                obj_name = attr["value"]
                break

        match.aris_guid = best_obj["guid"]
        match.aris_name = obj_name
        match.aris_type = best_obj.get("typename", "")
        match.aris_type_num = best_obj.get("type")
        match.aris_symbol = best_obj.get("symbolname", "")
        match.match_score = best_score
        match.match_level = 2
        match.match_method = f"Fuzzy match (score: {best_score:.1f})"
        match.operation = "REUSE"
        match.candidates = sorted(candidates, key=lambda x: x["score"], reverse=True)[:5]
    
    elif candidates:
        # Livello 3: LLM sceglie tra candidati incerti
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
        else:
            # LLM dice NESSUNO → flag umano
            match.match_score = best_score
            match.match_level = 4
            match.match_method = f"LLM: nessun match sicuro tra {len(sorted_candidates)} candidati"
            match.operation = "FLAG_REVIEW"
            match.candidates = sorted_candidates
            match.warnings.append(f"LLM non ha trovato corrispondenze tra {len(sorted_candidates)} candidati.")
    
    else:
        # Nessun candidato → probabile nuovo oggetto
        match.match_score = 0
        match.match_level = 4
        match.match_method = "Nessun candidato trovato"
        match.operation = "CREATE"
        match.warnings.append("Oggetto non trovato nel database. Potrebbe essere nuovo.")

    return match


# ============================================================
# REPORT GENERATOR
# ============================================================

def generate_html_report(matches: list[ARISMatch], model_name: str) -> str:
    """Genera un report HTML con i risultati del matching."""

    level_colors = {
        1: ("#F0FFF4", "#38A169", "Match esatto"),
        2: ("#E6FFFA", "#028090", "Fuzzy match"),
        3: ("#FFFAF0", "#C05621", "LLM contestuale"),
        4: ("#FFF5F5", "#E53E3E", "Revisione richiesta"),
    }

    html = """<html><head><meta charset="utf-8"><style>
body{font-family:Calibri,sans-serif;margin:40px;color:#1a202c;max-width:1200px}
h1{color:#1E2761} h2{color:#028090}
table{border-collapse:collapse;width:100%;margin:16px 0}
th{background:#1E2761;color:white;padding:10px 14px;text-align:left}
td{padding:8px 14px;border-bottom:1px solid #ddd;vertical-align:top}
tr:nth-child(even){background:#f8f9fa}
.level{display:inline-block;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:bold}
.guid{font-family:monospace;font-size:11px;color:#666}
.op{font-weight:bold;padding:2px 8px;border-radius:4px;font-size:12px}
.op-reuse{background:#F0FFF4;color:#38A169}
.op-create{background:#EBF8FF;color:#2B6CB0}
.op-flag{background:#FFF5F5;color:#E53E3E}
.warn{color:#E53E3E;font-size:12px}
.stat{background:#1E2761;color:white;padding:12px 20px;border-radius:8px;margin:8px 4px;display:inline-block}
.stat b{color:#F6AD55;font-size:22px}
.candidates{font-size:11px;color:#888;margin-top:4px}
</style></head><body>"""

    html += f"<h1>ARIS Resolver Report</h1>"
    html += f"<p>Modello: <b>{model_name}</b></p>"

    # Statistiche
    by_level = defaultdict(int)
    by_op = defaultdict(int)
    for m in matches:
        by_level[m.match_level] += 1
        by_op[m.operation] += 1

    html += "<div>"
    html += f'<span class="stat">Entità analizzate: <b>{len(matches)}</b></span>'
    for lv in [1, 2, 3, 4]:
        if by_level[lv] > 0:
            _, color, label = level_colors[lv]
            html += f'<span class="stat">{label}: <b>{by_level[lv]}</b></span>'
    html += "</div>"

    # Tabella per tipo di entità
    for etype, elabel in [('activity', 'Attività (Function)'), ('executor', 'Esecutori (Org. Unit)'),
                           ('application', 'Applicativi'), ('control', 'Controlli')]:
        ematches = [m for m in matches if m.word_entity.entity_type == etype]
        if not ematches:
            continue

        html += f"<h2>{elabel} — {len(ematches)} entità</h2>"
        html += "<table><tr><th>Word</th><th>ARIS Match</th><th>GUID</th><th>Livello</th><th>Score</th><th>Operazione</th></tr>"

        for m in ematches:
            bg, color, label = level_colors.get(m.match_level, ("#FFF", "#000", "?"))
            op_class = "op-reuse" if m.operation == "REUSE" else "op-create" if m.operation == "CREATE" else "op-flag"

            code_str = f"[{m.word_entity.code}] " if m.word_entity.code else ""
            html += f'<tr><td><b>{code_str}{m.word_entity.name}</b>'
            if m.warnings:
                for w in m.warnings:
                    html += f'<br><span class="warn">⚠ {w}</span>'
            html += "</td>"
            html += f'<td>{m.aris_name or "—"}</td>'
            html += f'<td class="guid">{m.aris_guid or "—"}</td>'
            html += f'<td><span class="level" style="background:{bg};color:{color}">{label}</span></td>'
            html += f'<td>{m.match_score:.0f}%</td>'
            html += f'<td><span class="op {op_class}">{m.operation}</span></td></tr>'

        html += "</table>"

    html += "</body></html>"
    return html


# ============================================================
# MAIN
# ============================================================

def main():
    """
    Flusso principale del Resolver POC.

    Per il POC, usa il contenuto del modello ARIS già estratto via API
    come database di oggetti contro cui fare il matching.
    In produzione, il Resolver farà query live all'API per ogni entità.
    """
    import sys

    print("=" * 60)
    print("  ARIS RESOLVER - Prototipo v0.1")
    print("=" * 60)
    print()

    # --- Passo 1: Leggi il Word ---
    word_file = sys.argv[1] if len(sys.argv) > 1 else None
    if not word_file:
        print("Uso: python resolver_poc.py <file_word> [file_model_json]")
        print("  file_word: il .doc/.docx del PO")
        print("  file_model_json: (opzionale) il JSON del modello ARIS estratto via API")
        sys.exit(1)

    print(f"[1/4] Lettura Word: {word_file}")
    if word_file.endswith('.doc'):
        from striprtf.striprtf import rtf_to_text
        with open(word_file, 'r', encoding='cp1252', errors='replace') as f:
            text = rtf_to_text(f.read())
    else:
        # Per .docx, usa python-docx
        import docx
        doc = docx.Document(word_file)
        text = "\n".join(p.text for p in doc.paragraphs)

    entities = extract_entities_from_word_text(text)
    print(f"    Entità estratte: {len(entities)}")
    for etype in ['activity', 'executor', 'application', 'control']:
        count = len([e for e in entities if e.entity_type == etype])
        if count > 0:
            print(f"      - {etype}: {count}")

    # --- Passo 2: Carica gli oggetti ARIS ---
    model_json_file = sys.argv[2] if len(sys.argv) > 2 else None
    aris_objects = []

    if model_json_file:
        print(f"\n[2/4] Caricamento oggetti ARIS da file: {model_json_file}")
        with open(model_json_file, 'r') as f:
            model_data = json.load(f)
        model = model_data['items'][0]
        model_name = "?"
        for attr in model.get('attributes', []):
            if attr.get('apiname') == 'AT_NAME':
                model_name = attr['value']
                break

        # Estrai oggetti unici (per GUID) dal modello
        seen_guids = set()
        for obj in model.get('modelobjects', []):
            if obj['guid'] not in seen_guids:
                seen_guids.add(obj['guid'])
                aris_objects.append(obj)
        print(f"    Oggetti ARIS unici caricati: {len(aris_objects)}")
    else:
        print(f"\n[2/4] Connessione all'API ARIS...")
        client = ARISClient(ARIS_BASE_URL, ARIS_DB_NAME, ARIS_TENANT)
        if not client.login(ARIS_USER, ARIS_PASSWORD):
            print("ERRORE: impossibile connettersi ad ARIS.")
            sys.exit(1)

        # Cerca il modello
        model_name = "2.7.1.02 Incentivazione commerciale"
        print(f"    Ricerca modello: {model_name}")
        # ... qui faremo la ricerca live in futuro
        client.logout()
        print("    (Modalità live API non ancora implementata. Usa il file JSON.)")
        sys.exit(0)

    # --- Passo 3: Matching ---
    print(f"\n[3/4] Matching entità Word → ARIS")
    matches = []
    for entity in entities:
        match = match_entity_against_aris(entity, aris_objects)
        matches.append(match)

        level_emoji = {1: "✅", 2: "🔶", 3: "🤖", 4: "❌"}
        emoji = level_emoji.get(match.match_level, "?")
        print(f"    {emoji} [{entity.entity_type[:4]}] \"{entity.name}\" → ", end="")
        if match.aris_guid:
            print(f"MATCH L{match.match_level} ({match.match_score:.0f}%) → \"{match.aris_name}\"")
        else:
            print(f"NESSUN MATCH → {match.operation}")

    # --- Passo 4: Report ---
    print(f"\n[4/4] Generazione report")
    report_html = generate_html_report(matches, model_name)
    report_path = word_file.rsplit('.', 1)[0] + "_resolver_report.html"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_html)
    print(f"    Report salvato: {report_path}")

    # Riepilogo
    print(f"\n{'=' * 60}")
    print(f"  RIEPILOGO")
    print(f"{'=' * 60}")
    reuse = len([m for m in matches if m.operation == "REUSE"])
    create = len([m for m in matches if m.operation == "CREATE"])
    flag = len([m for m in matches if m.operation == "FLAG_REVIEW"])
    print(f"  Entità totali:     {len(matches)}")
    print(f"  REUSE (trovate):   {reuse}")
    print(f"  CREATE (nuove):    {create}")
    print(f"  FLAG (da rivedere): {flag}")
    print()


if __name__ == "__main__":
    main()
