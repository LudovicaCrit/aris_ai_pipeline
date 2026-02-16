# Process Comparator

Agente per l'analisi comparativa di processi aziendali (As-Is vs To-Be) esportati da ARIS.

## Funzionalità

- **Parsing automatico** di documenti ARIS (.doc/.docx/.txt)
- **Confronto strutturale** tra versione As-Is e To-Be
- **Calcolo metriche quantitative**:
  - Volatility Index (attività aggiunte/rimosse)
  - Handover Delta (passaggi di mano tra unità organizzative)
  - Automation Rate Delta (transizioni manuale → digitale)
  - Process Change Score (PCS) composito
- **Analisi qualitativa** tramite LLM (Google Gemini, OpenAI, Anthropic)
- **Rilevamento anomalie semantiche** (contenuti fuori contesto, esecutori implausibili)
- **Generazione report Word** professionale
- **Elaborazione batch asincrona** per volumi elevati

## Installazione

### Prerequisiti

```bash
# Dipendenze di sistema (per parsing .doc)
sudo apt-get install antiword

# Python dependencies
pip install -r requirements.txt
```

### Configurazione API Key

Crea un file `.env` nella root del progetto:

```bash
# Google AI (Gemini) - raccomandato
GEMINI_API_KEY=your-api-key-here

# Oppure usa GOOGLE_API_KEY (equivalente)
# GOOGLE_API_KEY=your-api-key-here

# Altri provider (opzionali)
# LLM_PROVIDER=openai
# OPENAI_API_KEY=your-api-key

# LLM_PROVIDER=anthropic  
# ANTHROPIC_API_KEY=your-api-key
```

## Utilizzo

### Singolo confronto

```bash
# Analisi completa (metriche + LLM + report Word)
python main.py processo_as_is.txt processo_to_be.txt

# Solo metriche (senza LLM, veloce)
python main.py as_is.txt to_be.txt --metrics-only

# Specificare file di output
python main.py as_is.txt to_be.txt -o report_finale.docx

# Output JSON invece di Word
python main.py as_is.txt to_be.txt --json

# Verbose mode
python main.py as_is.txt to_be.txt -v
```

### Batch processing (multipli confronti)

#### Modalità interattiva
```bash
python batch_interactive.py --as-is-dir ./as_is --to-be-dir ./to_be
```

#### Modalità asincrona (parallela) - RACCOMANDATA per volumi elevati
```bash
# Analisi completa parallela
python batch_async.py --as-is-dir ./as_is --to-be-dir ./to_be --output-dir ./output

# Solo metriche (senza LLM)
python batch_async.py --as-is-dir ./as_is --to-be-dir ./to_be --metrics-only

# Configurare parallelismo (default: 5 chiamate LLM simultanee)
python batch_async.py --as-is-dir ./as_is --to_be-dir ./to_be --max-concurrent 10
```

### Performance batch async

| N. documenti | Sequenziale | Parallelo (5 thread) | Speedup |
|--------------|-------------|----------------------|---------|
| 10           | ~50 sec     | ~10 sec              | 5x      |
| 50           | ~4 min      | ~50 sec              | 5x      |
| 100          | ~8 min      | ~1.5 min             | 5x      |

## Architettura

```
┌─────────────────────────────────────────────────────────────┐
│                        INPUT                                 │
│   As-Is.doc/txt  ─────────────────────  To-Be.doc/txt       │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
               ▼                              ▼
┌──────────────────────────────────────────────────────────────┐
│                  FASE 1: PARSING (Python)                    │
│   document_parser.py - Estrae attività, esecutori, sistemi   │
│   Tempo: ~10ms per documento                                 │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                   FASE 2: DIFF (Python)                      │
│   diff_engine.py - Confronta strutture, rileva modifiche     │
│   Tempo: ~5ms per coppia                                     │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                 FASE 3: METRICHE (Python)                    │
│   metrics.py - Calcola PCS, Volatility, Handover             │
│   Tempo: ~1ms                                                │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│              FASE 4: ANALISI LLM (API async)                 │
│   langchain_agent.py - Interpretazione qualitativa           │
│   - Analisi impatto business                                 │
│   - Rilevamento anomalie semantiche                          │
│   - Raccomandazioni                                          │
│   Tempo: ~3-5 sec per documento (parallelizzabile)           │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                  FASE 5: OUTPUT (Python)                     │
│   report_generator.py - Genera Word/JSON                     │
│   Tempo: ~100ms per report                                   │
└──────────────────────────────────────────────────────────────┘
```

## Metriche

### Volatility Index (SVI)
Percentuale di task aggiunti o eliminati rispetto al totale originale.

| Livello | Soglia |
|---------|--------|
| Alta    | > 30%  |
| Media   | 1-30%  |
| Bassa   | < 1%   |

### Handover Delta
Variazione dei passaggi di mano tra unità organizzative diverse.

### Automation Rate Delta
Percentuale di task che passano da manuali a digitali (o viceversa).

### Process Change Score (PCS)
Score composito calcolato come:

```
PCS = (Volatility × 0.50) + (Handover × 0.40) + (Automation × 0.10)
```

| PCS     | Livello  | Azione              |
|---------|----------|---------------------|
| ≥ 0.7   | Critico  | Audit obbligatorio  |
| 0.5-0.7 | Alto     | Audit raccomandato  |
| 0.2-0.5 | Medio    | Review standard     |
| < 0.2   | Basso    | Nessuna azione      |

## Rilevamento Anomalie

L'agente LLM analizza semanticamente le modifiche per rilevare:

- **Esecutori implausibili**: nomi di unità organizzative che non seguono pattern aziendali
- **Sistemi IT sospetti**: applicativi con nomi non coerenti col contesto enterprise
- **Contenuti fuori contesto**: descrizioni o titoli con riferimenti non pertinenti
- **Placeholder dimenticati**: testo di test lasciato in produzione

L'analisi semantica è delegata interamente all'LLM, senza regex hardcodate.

## Struttura Progetto

```
process_comparator/
├── .env                          # API keys (da creare)
├── main.py                       # Entry point singolo confronto
├── batch_interactive.py          # Batch interattivo
├── batch_async.py                # Batch parallelo (async)
├── config.py                     # Configurazione
├── requirements.txt
│
├── prompts/
│   ├── system_prompt.md          # Identità e competenze agente
│   └── analysis_instructions.md  # Istruzioni struttura analisi
│
├── core/
│   ├── __init__.py
│   ├── document_parser.py        # Parser documenti ARIS
│   ├── diff_engine.py            # Motore di confronto
│   └── metrics.py                # Calcolo KPI
│
├── agent/
│   ├── __init__.py
│   └── langchain_agent.py        # Agente LangChain (sync + async)
│
├── output/
│   ├── __init__.py
│   └── report_generator.py       # Generatore Word
│
└── test_data/                    # Dati di test
    ├── as_is/
    └── to_be/
```

## Scenari di Test Inclusi

| Scenario | Documento | Tipo modifica | PCS atteso |
|----------|-----------|---------------|------------|
| 1        | 2.4.04    | 3 titoli modificati | Basso |
| 2        | 2.4.02    | 3 descrizioni modificate | Basso |
| 3a       | 2.4.01    | 3 esecutori (esistenti) | Medio |
| 3b       | 2.3.3.23  | 3 esecutori (nuovi) | Basso |
| 4        | 2.4.06    | 2 attività eliminate | Basso |
| 5        | 2.12.2.03 | 2 attività inserite | Alto |
| 6        | 2.12.2.01 | 2 scambi ordine | Medio |
| 7        | 2.2.2.17  | Nome processo | Basso |
| Mix      | 2.3.04.03 | 6 modifiche combinate | Alto |
| Anomalie | 2.2.3 BHC | Contenuti assurdi | - |

## Sviluppo Futuro

- [ ] Cache per documenti già analizzati
- [ ] Batch API per ridurre chiamate
- [ ] Integrazione RAG per contesto normativo
- [ ] Dashboard web per visualizzazione
- [ ] Validazione contro organigramma aziendale
- [ ] Export PDF oltre a Word
