# ARIS Resolver

Matching automatico tra entità dei Word dei Process Owner e oggetti nel database ARIS.

## Struttura

```
aris_resolver/
├── main.py              ← entry point
├── config.py            ← configurazione e soglie
├── models.py            ← dataclass (WordEntity, ARISMatch)
├── aris_client.py       ← client API REST ARIS (puro Python)
├── word_parser.py       ← estrazione entità dal Word (puro Python)
├── resolver.py          ← orchestratore cascata matching
├── report.py            ← generazione report HTML
├── matching/
│   ├── exact.py         ← Livello 1: match esatto + contenimento
│   ├── fuzzy.py         ← Livello 2: fuzzy matching
│   └── llm_resolver.py  ← Livello 3: LLM (unico modulo con AI)
├── prompts/
│   └── resolver_prompt.py ← template prompt separati
├── data/                ← dati di input
│   ├── model_content.json
│   └── word_samples/
├── output/              ← report generati
├── requirements.txt
└── .env                 ← chiavi API (non committare!)
```

## Principi architetturali

- **Separazione determinismo/AI**: solo `matching/llm_resolver.py` usa l'LLM
- **Cascata**: esatto → fuzzy → LLM → flag umano
- **L'LLM non inventa**: sceglie solo tra candidati esistenti o dice NESSUNO
- **Prompt separati**: in `prompts/`, iterabili senza toccare la logica

## Uso

```bash
source ../.venv_linux/bin/activate
python3 main.py "data/word_samples/file.doc" data/model_content.json
```

## Dipendenze

```bash
pip install -r requirements.txt
```
