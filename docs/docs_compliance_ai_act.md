# Profilo di Compliance AI — ARIS AI Pipeline

Classificazione del rischio e garanzie ai sensi del Regolamento UE 2024/1689 (AI Act).
Aggiornato a febbraio 2026.

> **Perimetro**: questo documento analizza esclusivamente la componente AI del sistema. La conformità GDPR, normativa assicurativa e sicurezza informatica esula dal presente perimetro e rientra nelle competenze dei rispettivi referenti aziendali.

## 1. Classificazione del rischio

### Il sistema NON rientra tra i sistemi ad alto rischio

L'Annex III dell'AI Act elenca le categorie di sistemi ad alto rischio. Quelle potenzialmente rilevanti in ambito assicurativo:

- **Categoria 4 — "Employment, workers management"**: sistemi AI per recruiting, valutazione performance, assegnazione compiti basata su tratti personali.
- **Categoria 5 — "Access to essential services"**: sistemi AI per credit scoring, valutazione rischio assicurativo, triage sanitario.

ARIS AI Pipeline non rientra in nessuna di queste categorie. Né ProcedureCheck né Resolver prendono decisioni su persone fisiche. Entrambi operano su metadati di processo aziendale (nomi di attività, unità organizzative, applicativi, descrizioni di flussi operativi) e producono output destinati a revisione umana.

### Esclusione esplicita: preparatory task

L'Art. 6(3)(d) dell'AI Act esclude dalla classificazione ad alto rischio i sistemi che "eseguono un compito preparatorio a una valutazione rilevante" senza sostituire il giudizio umano.

- **ProcedureCheck** produce un report di confronto. Il management valuta e decide. L'agente non approva né rifiuta modifiche.
- **Resolver** propone operazioni di aggiornamento. Un operatore verifica, approva o rifiuta ogni operazione.

### Classificazione risultante

**Rischio limitato/minimo.** L'unico obbligo applicabile è la trasparenza: gli operatori devono sapere che una componente AI è coinvolta. Questo è garantito dai report (vedi sezione 4).

## 2. Perimetro AI nei due agenti

| Aspetto | ProcedureCheck | Resolver |
|---|---|---|
| **Uso LLM** | Sostanziale: analisi semantica del confronto tra Word as-is e to-be | Marginale: solo Livello 3 della cascata, scelta tra max 5 candidati (<10% dei casi) |
| **Input all'LLM** | Testo procedurale dei documenti Word (non dati personali) | Nome entità + lista chiusa di max 5 candidati con GUID |
| **Output dell'LLM** | Report strutturato delle differenze | Un numero (indice candidato) o "NESSUNO" |
| **Decisioni autonome?** | No — il report è informativo, il management decide | No — le operazioni sono proposte, l'operatore decide |
| **Modifica database?** | No — non interagisce con ARIS | No — produce JSON per revisione umana |
| **Dati personali?** | No — testi procedurali (attività, flussi, responsabilità organizzative) | No — metadati di processo (nomi, GUID, tipi) |

In nessun caso l'AI prende decisioni autonome o opera su dati personali.

## 3. Garanzie di supervisione umana

Il sistema implementa human-in-the-loop a più livelli:

**1. Nessuna operazione irreversibile automatica.** Il Resolver produce un JSON con operazioni proposte. Nessuna scrittura sul database ARIS avviene senza approvazione. ProcedureCheck produce un report di lettura, senza effetti collaterali.

**2. CREATE sempre flaggato.** La creazione di nuovi oggetti nel database non è mai automatica: viene marcata come `REVIEW_NEW_OBJECT` e richiede approvazione esplicita. Requisito specifico di Reale Mutua.

**3. Match ambigui flaggati.** Quando l'LLM del Resolver non trova corrispondenza o il match è incerto, l'operazione viene marcata come `REVIEW_AMBIGUOUS_MATCH`.

**4. Trasparenza del processo decisionale.** Entrambi gli agenti producono output che documentano il ragionamento: ProcedureCheck nel report di confronto, Resolver nel report HTML con livello, score e metodo per ogni operazione.

**5. Logging completo.** Ogni operazione del Resolver include nel JSON: timestamp, livello di match, score, metodo utilizzato, candidati valutati, warnings. ProcedureCheck documenta le differenze riscontrate con riferimento al testo sorgente.

## 4. Trattamento dei dati

Entrambi gli agenti trattano esclusivamente contenuto procedurale aziendale: nomi di attività, descrizioni di flussi, unità organizzative, applicativi, GUID tecnici. Non vengono trattati dati personali di dipendenti, clienti o assicurati.

Le chiamate API al modello LLM trasmettono:
- **ProcedureCheck**: testo procedurale dei documenti Word (privo di dati personali)
- **Resolver**: nome dell'entità e una lista di massimo 5 candidati

Non vengono trasmessi documenti integrali contenenti informazioni riservate.

## 5. Modello AI utilizzato

Sviluppo: Gemini (Google). Produzione: Azure OpenAI, in conformità con l'infrastruttura cloud di Reale Mutua.

L'architettura è agnostica rispetto al provider. I punti di contatto con l'LLM sono isolati e l'interfaccia è intercambiabile senza modificare la logica applicativa.

I modelli LLM utilizzati sono General Purpose AI Models (GPAI) soggetti a obblighi propri ai sensi dell'Art. 53 dell'AI Act (trasparenza, documentazione tecnica). Questi obblighi ricadono sul provider del modello (Google/Microsoft), non sul deployer (IMC Group / Reale Mutua).

## 6. Sintesi

| Requisito | Stato |
|---|---|
| **Classificazione AI Act** | Rischio limitato/minimo — non rientra in Annex III |
| **Esclusione Art. 6(3)(d)** | Applicabile a entrambi gli agenti: preparatory task |
| **Trasparenza** | Garantita: report ProcedureCheck e report HTML + JSON del Resolver |
| **Supervisione umana** | Human-in-the-loop: nessuna operazione irreversibile automatica |
| **Dati personali** | Non trattati — solo contenuto procedurale e metadati di processo |
| **Ruolo dell'AI** | ProcedureCheck: analisi semantica (report informativo). Resolver: scelta tra candidati, <10% dei casi |
| **Obblighi GPAI (Art. 53)** | Ricadono sul provider del modello, non sul deployer |
| **Tracciabilità** | Completa per entrambi gli agenti |
| **GDPR e altre normative** | Fuori perimetro — competenza dei rispettivi referenti |
