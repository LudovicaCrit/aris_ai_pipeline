# ARIS Resolver

Matching automatico tra entità dei Word dei Process Owner e oggetti nel database ARIS.
Assegna i GUID corretti tramite una cascata deterministica a 4 livelli, con AI solo come fallback.

## Struttura

```
aris_resolver/
├── word_parser.py          Estrae entità dal Word (.doc RTF, .doc binario, .docx)
├── xml_parser.py           Parsa export AML (XML) da ARIS → formato interno
├── resolver.py             Orchestratore cascata di matching
├── matching/
│   ├── exact.py            Livello 1: match esatto + contenimento
│   ├── fuzzy.py            Livello 2: fuzzy matching (rapidfuzz)
│   └── llm_resolver.py     Livello 3: LLM sceglie tra candidati (unico modulo AI)
├── diff/
│   └── diff_engine.py      Scenario 3: confronto Word vs ARIS senza track changes
├── report.py               Report HTML per revisione umana
├── models.py               Dataclass (WordEntity, ARISMatch)
├── config.py               Soglie e configurazione
├── main.py                 Entry point standalone (alternativo al pipeline)
├── aris_client.py          Client API REST ARIS
├── prompts/
│   └── resolver_prompt.py  Template prompt separati dalla logica
├── data/
│   ├── model_content.json  Modello ARIS (JSON REST)
│   ├── xml_4_09_02.xml     Modello ARIS (export AML)
│   └── word_samples/       File Word di test
├── requirements.txt
└── .env                    Chiavi API (non committare!)
```

## Cascata di matching

Per ogni entità estratta dal Word, il Resolver cerca il GUID corrispondente in ARIS:

| Livello | Metodo | Cosa fa | AI? |
|---------|--------|---------|-----|
| 1a | Match esatto | Nome normalizzato identico nell'XML/SQLite | No |
| 1b | Contenimento | Un nome è contenuto nell'altro | No |
| 2 | Fuzzy | Similarità token-based ≥ 80% (rapidfuzz) | No |
| 3 | LLM | Sceglie tra candidati esistenti (60-80%) o NESSUNO | Sì |
| 4 | Flag umano | Nessun match → revisione obbligatoria | No |

Su 10 moduli, solo `matching/llm_resolver.py` usa l'AI. Nei test, il 90%+ delle entità viene risolto al Livello 1.

## Formati supportati

| Input | Formato | Metodo |
|-------|---------|--------|
| Word (.doc RTF) | RTF | striprtf |
| Word (.doc binario) | OLE2 | antiword |
| Word (.docx) | OOXML | python-docx |
| ARIS model (.json) | JSON REST API | json.load |
| ARIS model (.xml/.aml) | Export AML | xml_parser.py |

## Uso

```bash
# Uso standalone (entry point diretto)
source ../.venv_linux/bin/activate
python3 main.py "data/word_samples/file.docx" data/model_content.json

# Uso raccomandato: tramite il pipeline (auto-detect JSON/XML)
cd ../pipeline
python3 pipeline.py "../aris_resolver/data/word_samples/file.docx" "../aris_resolver/data/xml_4_09_02.xml"
```

## Principi architetturali

- **Separazione determinismo/AI**: solo `matching/llm_resolver.py` usa l'LLM
- **Cascata**: esatto → fuzzy → LLM → flag umano, si ferma al primo match
- **L'LLM non inventa**: sceglie solo tra candidati esistenti o dice NESSUNO
- **CREATE mai automatico**: richiede approvazione umana (requisito Reale Mutua)
- **Prompt separati**: in `prompts/`, iterabili senza toccare la logica
- **Provider-agnostico**: sviluppo con Gemini, produzione su Azure OpenAI

## Dipendenze

```bash
sudo apt install antiword
pip install -r requirements.txt
```