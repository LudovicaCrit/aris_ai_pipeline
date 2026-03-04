# Architettura — ARIS AI Pipeline

Documento tecnico di riferimento. Versione 0.3, febbraio 2026.

## Panoramica

Il sistema è composto da due agenti indipendenti orchestrati da `pipeline.py`:

| | ProcedureCheck | Resolver |
|---|---|---|
| **Richiesto da** | Reale Mutua (requisito originario) | IMC Group (estensione tecnica) |
| **Input** | Word as-is + Word to-be | Word to-be + modello ARIS (XML o JSON) |
| **Output** | Report Word delle differenze | JSON operazioni ARIS + Report HTML |
| **Destinatario** | Management, governance | Operatore ARIS, team tecnico |
| **Uso LLM** | Sostanziale (analisi semantica) | Marginale (<10% dei casi) |

Se un agente fallisce, l'altro continua.

## Cascata di matching del Resolver

Per ogni entità estratta dal Word (attività, esecutore, applicativo), il Resolver cerca il corrispondente oggetto ARIS e il suo GUID. La cascata si ferma al primo match trovato.

### Livello 1a — Match esatto

Il `word_parser` estrae il nome dal Word (es. "Condivisione bozza questionario"). Il nome viene normalizzato: minuscolo, rimozione punteggiatura, trim spazi. Se un oggetto nell'XML ha lo stesso nome normalizzato, il GUID viene assegnato immediatamente. Nessuna AI, nessuna ambiguità.

- Modulo: `matching/exact.py` → `exact_match()`
- Score: 100%
- Normalizzazione: `re.sub(r'[^\w\s]', '', name.lower().strip())`

### Livello 1b — Contenimento

Se un nome è contenuto nell'altro (es. "GROUP ACADEMY" dentro "GROUP ACADEMY - Office"), match con guardie di sicurezza.

- Modulo: `matching/exact.py` → `containment_match()`
- Score: 95%
- Guardie: lunghezza minima 4 caratteri (`CONTAINMENT_MIN_LENGTH`), rapporto corto/lungo ≥ 0.5 (`CONTAINMENT_MIN_RATIO`)

### Livello 2 — Fuzzy matching

Calcola la similarità token-based con rapidfuzz (`token_sort_ratio`). Se ≥ 80% (`FUZZY_MATCH_THRESHOLD`), assegna il GUID. Copre errori di battitura, abbreviazioni, suffissi diversi. Ancora deterministico, zero AI.

- Modulo: `matching/fuzzy.py` → `fuzzy_match()`
- Score: 80-99%
- Libreria: rapidfuzz (implementazione C, veloce)

### Livello 3 — LLM

Se il fuzzy trova candidati nella zona incerta (60-80%, tra `FUZZY_UNCERTAIN_THRESHOLD` e `FUZZY_MATCH_THRESHOLD`), l'LLM riceve la lista chiusa (max 5 candidati) e sceglie il più plausibile, o risponde NESSUNO.

- Modulo: `matching/llm_resolver.py` → `llm_resolve()`
- Input: nome entità + lista candidati con GUID
- Output: un numero (indice) o "NESSUNO"
- Il prompt è in `prompts/resolver_prompt.py`, separato dalla logica
- LLM attuale: Gemini 2.5 Flash (sviluppo) → Azure OpenAI (produzione)

### Livello 4 — Flag umano

Nessun match trovato a nessun livello. L'entità viene flaggata per revisione umana. L'operatore decide se è un oggetto nuovo (CREATE) o un errore nel Word.

### Contesti di ricerca

I Livelli 1-2-3 cercano in due contesti progressivamente più ampi:

1. **XML del modello corrente** (disponibile) — contiene oggetti, connessioni e GUID del processo specifico. Sorgente primaria.
2. **Database SQLite completo** (futuro) — dump dell'intero database ARIS. Se un oggetto non è nel modello corrente ma esiste altrove (es. l'applicativo JAMIO), il SQLite lo trova ed evita un falso CREATE.

La cascata completa: esatto in XML → esatto in SQLite → fuzzy in XML → fuzzy in SQLite → LLM tra candidati → flag umano. L'AI interviene solo dopo quattro passaggi deterministici.

## Soglie di matching (config.py)

| Parametro | Valore | Dove |
|---|---|---|
| `EXACT_MATCH_THRESHOLD` | 100 | Score per match perfetto |
| `FUZZY_MATCH_THRESHOLD` | 80 | Score minimo per match automatico (L2) |
| `FUZZY_UNCERTAIN_THRESHOLD` | 60 | Sotto: nessun candidato per L3 |
| `CONTAINMENT_MIN_LENGTH` | 4 | Lunghezza minima per contenimento |
| `CONTAINMENT_MIN_RATIO` | 0.5 | Rapporto min corto/lungo |

## Confronto connessioni (R6)

Quando l'input è XML (export AML), il sistema ha accesso alle `CxnDef` (connessioni). Questo permette di confrontare le relazioni esecutore→attività tra Word (to-be) e ARIS (as-is) per GUID, identificando:

- **OK**: stesso esecutore in Word e ARIS
- **CHANGED**: esecutore diverso (cambio di responsabilità)
- **NEW**: attività nuova, non presente in ARIS
- **NEW_CONNECTION**: attività esiste ma non ha connessione esecutore in ARIS

Il confronto avviene in `compare_connections()` dentro `pipeline.py`.

## Formati Word supportati

Il `word_parser.py` gestisce tre formati con tre metodi diversi:

| Formato | Riconoscimento | Metodo | Separatore blocchi |
|---|---|---|---|
| .doc RTF | `striprtf` estrae testo con TITOLO | striprtf | `\n010\|TITOLO` (pipe) |
| .doc binario | fallback se striprtf fallisce | antiword | `010\x07TITOLO` (bell char) |
| .docx | estensione .docx | python-docx | `010TITOLO` (nessuno) |

La regex sceglie il ramo corretto in base alla presenza di `\x07` (bell) o `|` (pipe) nel testo.

## Auto-detect formato ARIS

`detect_format()` in `pipeline.py` determina se il file è JSON o XML:
1. Per estensione (.json / .xml / .aml)
2. Se ambiguo: sniffa i primi 500 byte

`load_aris_model_from_xml()` chiama `xml_parser.parse_xml()` e costruisce un `model_data_compat` con la stessa struttura del JSON REST. Così `compare_connections()`, `build_update_json()` e `run_diff_engine()` funzionano identici indipendentemente dal formato.

## Policy operative

- **CREATE mai automatico** — la creazione di nuove definizioni richiede approvazione umana (requisito Reale Mutua)
- **UPDATE solo se verificato** — `build_update_json()` confronta realmente la descrizione Word vs ARIS prima di generare un UPDATE. Se identiche: UNCHANGED
- **Logging completo** — ogni operazione nel JSON include: livello, score, metodo, candidati valutati, warnings, timestamp

## Moduli e dipendenze AI

| Modulo | AI? | Note |
|---|---|---|
| `word_parser.py` | No | Parsing deterministico |
| `xml_parser.py` | No | Parsing XML |
| `matching/exact.py` | No | L1: esatto + contenimento |
| `matching/fuzzy.py` | No | L2: rapidfuzz |
| `matching/llm_resolver.py` | **Sì** | L3: unico punto di contatto LLM |
| `resolver.py` | No | Orchestratore cascata |
| `pipeline.py` | No | Entry point, auto-detect |
| `diff/diff_engine.py` | No | Scenario 3 |
| `report.py` | No | Report HTML |
| `core/diagram_analyzer.py` | **Sì** | ProcedureCheck: analisi semantica |
| `agent/langchain_agent.py` | **Sì** | ProcedureCheck: agente multi-step |

Su ~15 moduli totali, 3 usano l'AI. Tutti gli altri sono deterministici, verificabili, riproducibili.

## Risultati empirici

Test sul modello 4.09.02 (Analisi del fabbisogno formativo), febbraio 2026:

- 12 entità estratte dal Word to-be
- 10 risolte al Livello 1 (deterministico, zero AI)
- 1 flaggata come nuova attività: "Approvazione questionario da parte del dirigente" → FLAG_REVIEW (correttamente, non esiste nell'as-is)
- 1 flaggata come nuovo applicativo: "JAMIO" → CREATE (esiste altrove nel database, sarà coperta dal SQLite)
- 2 cambi connessione rilevati (cambio esecutore su "Condivisione bozza" e "Verificare corretto funzionamento")
