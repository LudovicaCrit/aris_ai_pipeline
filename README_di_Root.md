# ARIS AI Pipeline

Automazione dell'allineamento tra documenti procedurali (Word dei Process Owner) e database ARIS.

**Due agenti indipendenti, un pipeline unico.**

## Architettura

```
aris_ai_pipeline/
├── pipeline/                      ← Orchestratore v0.3
│   └── pipeline.py                   Entry point unico, auto-detect JSON/XML
│
├── aris_resolver/                 ← Agente 2: Entity Resolution
│   ├── word_parser.py                Estrae entità dal Word (.doc RTF, .doc binario, .docx)
│   ├── xml_parser.py                 Parsa export AML (XML) da ARIS
│   ├── resolver.py                   Orchestratore cascata di matching
│   ├── matching/
│   │   ├── exact.py                  Livello 1: match esatto + contenimento
│   │   ├── fuzzy.py                  Livello 2: fuzzy matching (rapidfuzz)
│   │   └── llm_resolver.py          Livello 3: LLM tra candidati (unico modulo AI)
│   ├── diff/
│   │   └── diff_engine.py            Scenario 3: confronto Word vs ARIS senza track changes
│   ├── report.py                     Report HTML per revisione umana
│   ├── models.py                     Dataclass (WordEntity, ARISMatch)
│   ├── config.py                     Soglie e configurazione
│   └── data/                         File di test (XML, JSON, Word samples)
│
└── process_comparator_affinato/   ← Agente 1: ProcedureCheck
    ├── core/                         Parsing, confronto, metriche
    ├── agent/                        Agente LangChain per analisi multi-step
    ├── prompts/                      Template prompt separati dalla logica
    ├── main.py                       Entry point standalone
    └── batch_async.py                Elaborazione batch asincrona
```

## I due agenti

### ProcedureCheck (richiesto da Reale Mutua)
Confronta il documento procedurale originale (as-is) con la versione modificata (to-be). Produce un report Word con le differenze per il management. Usa l'LLM per analisi semantica del confronto.

### Resolver (estensione tecnica IMC Group)
Identifica quali oggetti nel database ARIS corrispondono alle entità nel Word del Process Owner, assegnando i GUID corretti. Produce un JSON con operazioni proposte (UPDATE, REUSE, CREATE, FLAG_REVIEW).

L'AI generativa è confinata al Livello 3 della cascata e interviene solo quando i metodi deterministici (Livelli 1-2) non trovano un match sicuro. Nei test, il 90%+ delle entità viene risolto senza AI.

## Cascata di matching del Resolver

```
Word to-be                       ARIS (XML/JSON)
     │                                │
     ▼                                ▼
 word_parser                    xml_parser / json
     │                                │
     └──────────┐  ┌──────────────────┘
                ▼  ▼
           ┌─────────────┐
           │  Livello 1a  │  Match esatto (nome normalizzato) ──→ GUID ✓
           │  Livello 1b  │  Contenimento (abbreviazione)     ──→ GUID ✓
           ├─────────────┤
           │  Livello 2   │  Fuzzy matching (≥80%)             ──→ GUID ✓
           ├─────────────┤
           │  Livello 3   │  LLM sceglie tra candidati         ──→ GUID ✓
           ├─────────────┤
           │  Livello 4   │  Flag per revisione umana          ──→ REVIEW
           └─────────────┘
```

Ogni livello cerca prima nell'XML del modello corrente, poi (futuro) nel database SQLite completo di ARIS. L'LLM non inventa oggetti: riceve una lista chiusa di candidati e sceglie, o risponde NESSUNO.

## Uso

```bash
# Attiva l'ambiente
source .venv_linux/bin/activate

# Solo Resolver — auto-detect JSON o XML
cd pipeline
python3 pipeline.py "../aris_resolver/data/word_samples/file.docx" "../aris_resolver/data/model.xml"

# Resolver + ProcedureCheck
python3 pipeline.py "to-be.docx" "model.xml" --as-is "as-is.doc"

# Resolver + Diff Engine (Scenario 3)
python3 pipeline.py "to-be.docx" "model.xml" --scenario3
```

## Formati supportati

| Input | Formato | Metodo |
|-------|---------|--------|
| Word (.doc RTF) | RTF | striprtf |
| Word (.doc binario) | OLE2 | antiword |
| Word (.docx) | OOXML | python-docx |
| ARIS model (.json) | JSON REST API | json.load |
| ARIS model (.xml/.aml) | Export AML | xml_parser.py |

## Policy operative

- **CREATE mai automatico** — la creazione di nuovi oggetti richiede approvazione umana
- **UPDATE solo se verificato** — confronto reale degli attributi prima di generare un UPDATE
- **Logging completo** — ogni operazione include livello, score, metodo, candidati

## Dipendenze

```bash
# Sistema
sudo apt install antiword

# Python
pip install -r aris_resolver/requirements.txt
pip install -r process_comparator_affinato/requirements.txt
```

## Stato

- [x] ProcedureCheck: confronto Word as-is vs to-be
- [x] Resolver: cascata 4 livelli con matching GUID
- [x] Pipeline v0.3: orchestrazione, auto-detect JSON/XML
- [x] Confronto connessioni (esecutore → attività) da XML
- [ ] Database SQLite completo (in discussione con il cliente)
- [ ] Batch testing massivo
- [ ] Migrazione LLM da Gemini ad Azure OpenAI

---

*Autore: Ludovica Ignatia Di Cianni — IMC Group*
*Per: Reale Mutua di Assicurazioni*
