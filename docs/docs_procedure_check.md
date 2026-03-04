# ProcedureCheck — Dettagli Tecnici

Documentazione tecnica dell'agente ProcedureCheck (process_comparator_affinato/).
Aggiornato a febbraio 2026.

## Pipeline di elaborazione

```
Word as-is + Word to-be
        │
        ▼
  FASE 1: Parsing (document_parser.py)
  Estrae attività, esecutori, sistemi IT, controlli.
  Supporta .doc RTF, .doc binario (antiword), .docx.
  Tempo: ~10ms per documento.
        │
        ▼
  FASE 2: Confronto strutturale (diff_engine.py)
  Rileva attività aggiunte, rimosse, modificate (titolo, descrizione,
  esecutore, applicativo). Matching per codice attività (010, 020, ...).
  Tempo: ~5ms per coppia.
        │
        ▼
  FASE 3: Calcolo metriche (metrics.py)
  Volatility Index, Handover Delta, Automation Rate Delta, PCS composito.
  Tempo: ~1ms.
        │
        ▼
  FASE 4: Analisi LLM (diagram_analyzer.py + langchain_agent.py)
  Interpretazione qualitativa delle differenze: impatto business,
  anomalie semantiche, raccomandazioni.
  Tempo: ~3-5 sec per documento.
        │
        ▼
  FASE 5: Generazione report Word
  Report professionale con metriche + analisi qualitativa.
  Tempo: ~100ms.
```

## Metriche quantitative

### Volatility Index (SVI)

Percentuale di attività aggiunte o rimosse rispetto al totale originale.

```
SVI = (attività_aggiunte + attività_rimosse) / attività_originali
```

| Livello | Soglia |
|---------|--------|
| Alta | > 30% |
| Media | 10% - 30% |
| Bassa | < 10% |

Soglie definite in `core/metrics.py`:
- `VOLATILITY_HIGH = 0.30`
- `VOLATILITY_MEDIUM = 0.10`

### Handover Delta

Variazione dei passaggi di mano tra unità organizzative diverse. Un handover si verifica quando due attività consecutive hanno esecutori diversi.

```
Handover Delta = handover_to_be - handover_as_is
```

Per il PCS, viene normalizzato: `abs(delta) / handover_as_is`, capped a 1.0.

### Automation Rate Delta

Variazione della percentuale di attività automatizzate (non manuali).

```
Automation Rate = (attività_totali - attività_manuali) / attività_totali
Delta = abs(rate_to_be - rate_as_is)
```

### Process Change Score (PCS)

Score composito che sintetizza le tre metriche:

```
PCS = (Volatility × 0.50) + (Handover_norm × 0.40) + (Automation_delta × 0.10)
```

Pesi definiti in `core/metrics.py`:
- `VOLATILITY_WEIGHT = 0.50`
- `HANDOVER_WEIGHT = 0.40`
- `AUTOMATION_WEIGHT = 0.10`

| PCS | Livello | Azione |
|-----|---------|--------|
| ≥ 0.7 | Critico | Audit obbligatorio |
| 0.5 - 0.7 | Alto | Audit raccomandato |
| 0.2 - 0.5 | Medio | Review standard |
| < 0.2 | Basso | Nessuna azione |

Nota: i quattro livelli e le soglie sono una proposta tecnica di IMC Group, non sono stati specificati dal cliente. Possono essere rivisti in fase di validazione.

## Rilevamento anomalie

L'agente LLM analizza semanticamente le modifiche per rilevare:

- **Esecutori implausibili**: nomi di unità organizzative che non seguono pattern aziendali (es. nomi propri invece di sigle organizzative)
- **Sistemi IT sospetti**: applicativi con nomi non coerenti col contesto enterprise
- **Contenuti fuori contesto**: descrizioni con riferimenti non pertinenti al processo
- **Placeholder dimenticati**: testo di test lasciato in produzione

L'analisi è delegata interamente all'LLM, senza regex hardcodate. I prompt sono in `prompts/system_prompt.md` e `prompts/analysis_instructions.md`.

## Scenari di test

Scenari utilizzati durante lo sviluppo iniziale (gennaio-febbraio 2026). Questa lista verrà estesa con i batch di testing successivi.

| Scenario | Documento | Tipo modifica | PCS atteso |
|----------|-----------|---------------|------------|
| 1 | 2.4.04 | 3 titoli modificati | Basso |
| 2 | 2.4.02 | 3 descrizioni modificate | Basso |
| 3a | 2.4.01 | 3 esecutori (esistenti) | Medio |
| 3b | 2.3.3.23 | 3 esecutori (nuovi) | Basso |
| 4 | 2.4.06 | 2 attività eliminate | Basso |
| 5 | 2.12.2.03 | 2 attività inserite | Alto |
| 6 | 2.12.2.01 | 2 scambi ordine | Medio |
| 7 | 2.2.2.17 | Nome processo | Basso |
| Mix | 2.3.04.03 | 6 modifiche combinate | Alto |
| Anomalie | 2.2.3 BHC | Contenuti assurdi | - |

I file di test sono in `Word_as_is/` (documenti originali) e `Word_to_be/` (versioni modificate).

## Batch processing

### Modalità asincrona (raccomandata)

```bash
python batch_async.py --as-is-dir ./Word_as_is --to-be-dir ./Word_to_be --output-dir ./output
```

Parametri:
- `--max-concurrent N`: numero di chiamate LLM parallele (default: 5)
- `--metrics-only`: solo metriche, senza LLM

Performance indicative:

| Documenti | Sequenziale | Parallelo (5) | Speedup |
|-----------|-------------|---------------|---------|
| 10 | ~50 sec | ~10 sec | 5x |
| 50 | ~4 min | ~50 sec | 5x |
| 100 | ~8 min | ~1.5 min | 5x |

Il collo di bottiglia è la latenza delle chiamate LLM, non il parsing o le metriche.

## Nota sul modello LLM

I moduli che usano l'LLM sono:
- `core/diagram_analyzer.py` — analisi semantica delle differenze
- `agent/langchain_agent.py` — orchestrazione multi-step

Sviluppo: Gemini (Google). Produzione: Azure OpenAI (infrastruttura Reale Mutua). Il provider è configurabile in `config.py` tramite la variabile `LLM_PROVIDER`.
