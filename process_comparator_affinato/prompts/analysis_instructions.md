# Analysis Instructions

## Input

You will receive:
1. **Structured diff data**: activities added, removed, modified; executor changes; IT system changes
2. **Pre-calculated metrics**: Volatility Index, Handover Delta, Automation Rate, Process Change Score (PCS)
3. **Diagram analysis (if available)**: Events, gateways, and flow description extracted from the process flow diagram

Do NOT recalculate metrics - use the values provided.

## CRITICAL: Using Diagram Events

**If diagram analysis is provided with events, you MUST use them.**

Events describe WHEN and WHY activities happen in the flow. There are two types:

### Internal Events
Events that belong to THIS process. Use them to describe when activities are triggered:
"[055] Notifica automatica - Attivata dall'evento 'Valutazione completata', questa attività invia..."

### Cross-Process Events
Events with a DIFFERENT process code (e.g., event "272.0 Generale" in process "2.7.1.02") indicate links to OTHER processes. These are valuable because they show how this process interfaces with others:
"[010] Richiesta iniziale - Questa attività è attivata dall'evento '272.0 Generale', che rappresenta un collegamento con il processo di Gestione Generale."

**How to identify cross-process events:**
- Event code differs significantly from the process code being analyzed
- Event names reference other business areas
- Events marked as "inizio" or "fine" with external codes

**Always mention cross-process events** - they reveal important dependencies between business processes.

Look for events that:
- Trigger the activity (inizio, richiesta ricevuta, approvazione completata...)
- Follow the activity (fine processo, notifica inviata...)
- Link to other processes (cross-process interfaces)
- Are decision points related to the activity

## Report Structure

Produce the report following this exact structure. All output must be in Italian.

---

### 1. RIEPILOGO

Write 3-5 sentences that summarize the changes detected in the process. This section must:

- Be **discorsive** (flowing prose, not a bullet list)
- Mention the **number and type** of changes (e.g., "Il processo presenta 2 attività rimosse e 3 modifiche agli esecutori")
- Reference specific activities by **code AND title** (e.g., "[030] Valutazione richiesta")
- State **observable facts only** - no interpretation of intent or consequences

Example of CORRECT summary:
"Il processo non presenta variazioni nel numero di attività, ma registra modifiche significative agli esecutori. Le attività [030] Valutazione richiesta deroga, [050] Verifica conformità e [070] Approvazione finale passano dai SERVIZI AMMINISTRATIVI TEAM 1 rispettivamente agli uffici ANTIRICICLAGGIO, COMPLIANCE e CONTROLLO INTERNO. L'Handover Delta aumenta di 5 unità, riflettendo i nuovi passaggi tra unità organizzative diverse."

Example of INCORRECT summary (do NOT write like this):
"Il processo è stato ottimizzato per migliorare i controlli interni. L'obiettivo appare essere il rafforzamento della compliance AML. Questi cambiamenti ridurranno il rischio operativo."

### 2. METRICHE

Present the metrics in a table with three columns: Metrica, Valore, Valutazione.

| Metrica | Valore | Valutazione |
|---------|--------|-------------|
| Volatility Index | X% | Bassa/Media/Alta |
| Handover Delta | +/-N (X -> Y) | Descrizione fattuale |
| Automation Rate | X% → Y% | Stabile/In aumento/In diminuzione |
| Process Change Score | X.XX | Basso/Medio/Alto |

**Thresholds for Volatility:**
- 0-10%: Bassa
- 11-30%: Media  
- >30%: Alta

**Thresholds for PCS:**
- < 0.2: Basso
- 0.2 - 0.5: Medio
- > 0.5: Alto

For Handover Delta and Automation Rate, describe the change factually (e.g., "Da 2 a 6 passaggi", "Invariata", "In aumento di 8 punti percentuali").

Do NOT add interpretive commentary after the table.

### 3. DETTAGLIO MODIFICHE

Organize changes into the following subsections. **Omit any subsection that has no changes.**

#### 3.1 Modifiche Strutturali e di Contenuto

**IMPORTANT: Generate a SINGLE markdown table with ALL activity changes. Do NOT use code blocks. Do NOT split the table.**

Format the table exactly like this, strictly ordered by activity code (010, 020, 030...):

| Codice | Titolo | Stato | Descrizione |
|--------|--------|-------|-------------|
| [020] | Nome attività | Aggiunta | Cosa FA questa nuova attività. Esecutore: NOME. |
| [030] | Nome attività | Rimossa | Cosa FACEVA. *Contenuti ereditati da [040]*. Era eseguita da: NOME. |
| [050] | Nome attività | Modificata | Cosa È CAMBIATO: titolo da "X" a "Y"; descrizione ora include Z; esecutore da A a B. |
| [060] | Nome attività | Riposizionata | Da 1° a 4° posizione nel flusso (su N attività totali). |

**CRITICAL - NO SEMANTIC JUDGMENTS**: Never comment on whether an activity "belongs" to this process or not. You don't have the full business context. Report what you find, don't judge whether it makes sense.

**Rules for the table:**
- **Aggiunta**: Describe what the activity DOES. Include executor. If diagram events available, mention trigger event.
- **Rimossa**: Describe what the activity DID. If content was inherited by another activity, mention it (e.g., "*Contenuti confluiti in [040]*"). Include former executor.
- **Modificata**: List ALL changes: title change, description change, executor change. Be specific about what changed.
- **Riposizionata**: Show old and new position in the flow (e.g., "Da 2° a 5° posizione su 7 attività"). This is critical for understanding flow changes!

**IMPORTANT - Content Inheritance**: When an activity is removed and a new activity has similar content, note this relationship.

**IMPORTANT - For Modificata activities**: Include executor changes here.

#### 3.1.1 Analisi del Flusso

**Include this subsection if there are ANY structural changes: activities added, removed, or reordered.**

Write a **narrative description** (4-8 sentences) of how the flow has changed. Be insightful but grounded in the data - explain the logical connections you observe, but don't invent motivations or business reasons not stated in the documents.

**For added activities:**
- Where does the new activity fit in the sequence?
- What logical role does it play between what comes before and after?
- What was likely implicit or missing before that is now explicit?

**For removed activities:**
- How does the flow proceed without this step?
- If content was inherited by another activity, explain the consolidation
- What does the removal suggest about process simplification or restructuring?

**For reordered activities:**
- How does the new order change the logic of the process?
- What gets validated/processed earlier or later now?

**End with the complete To-Be flow sequence** using arrows: [010] Nome → [020] Nome → [030] Nome...

**Style guidelines:**
- Be discorsive and readable, not mechanical
- Connect the dots - explain WHY a change makes sense in the context of the flow
- Stay grounded - only state what you can infer from the documents
- Use phrases like "questo suggerisce", "il flusso ora prevede", "la nuova sequenza permette"

Example:
"Il flusso To-Be introduce una gestione più articolata degli incident. Dopo la fase di registrazione [030], il processo ora prevede un passaggio dedicato di analisi [040] Analisi dell'issue, che consente di coinvolgere funzioni specialistiche prima di procedere alla risoluzione - un passaggio che nell'As-Is era probabilmente gestito in modo informale o incluso in altre attività. La nuova attività [060] Chiusura incident formalizza la comunicazione dell'esito agli interessati, rendendo esplicito un momento di chiusura che prima non era tracciato. Il flusso risultante è: [010] Ricezione segnalazione → [020] Valutazione preliminare → [030] Registrazione incident → [040] Analisi dell'issue → [060] Chiusura incident. Rispetto all'As-Is, il processo guadagna in tracciabilità e struttura, con fasi di analisi e chiusura ora chiaramente definite."

#### 3.2 Modifiche Organizzative

Describe changes to executors/organizational units. **Include full details** - this section should be self-contained.

Organize findings into these categories:

**Unità organizzative aggiunte** (new in To-Be):
- NOME UNITÀ: gestisce [CODE1] Titolo attività 1, [CODE2] Titolo attività 2

**Unità organizzative rimosse** (were in As-Is, gone in To-Be):
- NOME UNITÀ: non più presente nel processo (gestiva [CODE] Titolo attività)

**Unità organizzative con modifiche di competenza** (exist in both, but different activities):
- NOME UNITÀ: 
  - Acquisisce: [CODE1] Titolo (precedentemente gestita da ALTRA UNITÀ)
  - Perde: [CODE2] Titolo (ora gestita da ALTRA UNITÀ)
  - Mantiene: [CODE3] Titolo, [CODE4] Titolo

**Cambi di esecutore su singole attività**:
- [CODE] Titolo: esecutore da "VECCHIO" a "NUOVO"

Omit empty categories. Include activity titles for clarity.

#### 3.3 Modifiche Tecnologiche

List changes to IT systems (APPLICATIVO INFORMATICO field). **Explain HOW the system is used.**

Format:
- [CODE] TITLE: applicativo aggiunto NOME SISTEMA - descrivere brevemente l'uso (es: "per la generazione automatica di report mensili", "per la validazione dei dati anagrafici")
- [CODE] TITLE: applicativo rimosso NOME SISTEMA - indicare cosa gestiva prima
- [CODE] TITLE: applicativo da VECCHIO SISTEMA a NUOVO SISTEMA - spiegare il cambiamento

**Important**: If a new activity uses an IT system that already exists elsewhere in the process, still report it here with context on how it's being used in this specific activity.

#### 3.4 Modifiche Normative

**Only include this section if there are explicit changes to regulatory references in the document** (e.g., a reference changes from "D.Lgs 231/2001" to "D.Lgs 231/2001 e Reg. UE 679/2016").

Format:
- [CODE] TITLE: riferimento normativo da "VECCHIO" a "NUOVO"

If no regulatory references changed, omit this section entirely.

---

## Critical Rules

1. **Always use [CODE] TITLE format** when referencing activities - never just the code
2. **Omit empty sections** - if there are no structural changes, do not include section 3.1
3. **No speculation** - describe only what is visible in the data
4. **No recommendations** - do not suggest actions, audits, or follow-ups
5. **No risk assessment** - do not evaluate whether changes are positive or negative
6. **Factual valutazioni only** - in the metrics table, "Valutazione" means factual description (Bassa/Media/Alta, Stabile/In aumento), not judgment

## What NOT to Include

- Section "Risk and Compliance Notes" - omit entirely
- Section "Anomalie e Incongruenze" - omit entirely  
- Section "Recommendations" - omit entirely
- Any speculation about business intent or consequences
- Any judgment about whether changes are good or bad