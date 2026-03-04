# ProcedureCheck (Process Comparator)

Agente per l'analisi comparativa di processi aziendali (As-Is vs To-Be) esportati da ARIS.
Richiesto da Reale Mutua come strumento di supporto alla governance dei processi.

## Funzionalità

- **Parsing automatico** di documenti ARIS (.doc/.docx/.txt) tramite antiword, striprtf, python-docx
- **Confronto strutturale** tra versione As-Is e To-Be
- **Calcolo metriche quantitative** (Volatility Index, Handover Delta, Automation Rate Delta) con score composito PCS
- **Analisi qualitativa** tramite LLM (analisi semantica delle differenze)
- **Rilevamento anomalie semantiche** (contenuti fuori contesto, esecutori implausibili)
- **Generazione report Word** professionale
- **Elaborazione batch asincrona** per volumi elevati

Dettagli su formula PCS, soglie e scenari di test in `docs/procedure_check.md`.

## Struttura

```
process_comparator_affinato/
├── main.py                       Entry point singolo confronto
├── batch_interactive.py          Batch interattivo
├── batch_async.py                Batch parallelo (async)
├── config.py                     Configurazione e provider LLM
├── requirements.txt
│
├── core/
│   ├── document_parser.py        Parser universale documenti ARIS
│   ├── diff_engine.py            Motore di confronto strutturale
│   ├── diagram_analyzer.py       Analisi semantica differenze (LLM)
│   └── metrics.py                Calcolo KPI (PCS, Volatility, Handover)
│
├── agent/
│   └── langchain_agent.py        Agente LangChain per analisi multi-step
│
├── prompts/
│   ├── system_prompt.md          Identità e competenze agente
│   └── analysis_instructions.md  Istruzioni struttura analisi
│
├── Word_as_is/                   Documenti as-is per test
├── Word_to_be/                   Documenti to-be per test
├── data/                         Dati supplementari
└── test_data/                    Dati di test unitari
```

## Uso

### Singolo confronto

```bash
source ../.venv_linux/bin/activate

# Analisi completa (metriche + LLM + report Word)
python main.py processo_as_is.doc processo_to_be.doc

# Solo metriche (senza LLM, veloce)
python main.py as_is.doc to_be.doc --metrics-only

# Output JSON invece di Word
python main.py as_is.doc to_be.doc --json
```

### Batch processing

```bash
# Batch parallelo (raccomandato per volumi elevati)
python batch_async.py --as-is-dir ./Word_as_is --to-be-dir ./Word_to_be --output-dir ./output

# Solo metriche (senza LLM)
python batch_async.py --as-is-dir ./Word_as_is --to-be-dir ./Word_to_be --metrics-only
```

### Tramite il pipeline

```bash
cd ../pipeline
python3 pipeline.py "to-be.docx" "model.xml" --as-is "as-is.doc"
```

## Nota sul modello LLM

Sviluppo e testing: Gemini (Google). Produzione: Azure OpenAI, in conformità con l'infrastruttura cloud di Reale Mutua. I punti di contatto con l'LLM sono isolati in `core/diagram_analyzer.py` e `agent/langchain_agent.py`.

## Dipendenze

```bash
sudo apt install antiword
pip install -r requirements.txt
```