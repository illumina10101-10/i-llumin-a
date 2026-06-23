# GROWTH LOG — I-llumin-A

## 2026-06-13 — Audit iniziale SMM + pivot formato

### Cosa ho fatto
- Rimosso TikTok + Instagram dalla pipeline -> focus 100% YouTube Shorts
- Pivot formato: da 35-42s a **15-20s loopabile** (dati: watch% > durata)
- Aggiunto hook_text gigante schermo primi 2.5s (pattern interrupt +23% retention)
- Definita nicchia: "fatti scientifici impossibili ma veri" (vedi NICHE_STRATEGY.md)

### Cosa ho osservato
- Video migliore = polpo 25s (natura/animali, corto) -> conferma: corto + natura vince
- Formato vecchio 35-42s = troppo lungo = watch% basso = algoritmo non spinge
- Topic troppo sparsi (scienza/storia/cancro/notizie) = nessuna identità canale
- Analytics API non accessibili (token scope solo upload, serve re-auth youtube.readonly)

### Decisioni
- Stringere niche su scienza/natura "wow"
- Tutti i video ora loopabili 15-20s
- Prossimo test: misurare watch% nuovo formato vs vecchio nei prossimi 7 giorni

### TODO prossimo
- [x] Re-auth YouTube con scope readonly — FATTO
- [ ] Dopo 7 giorni: confronto retention vecchio vs nuovo formato
- [ ] Se natura/animali outperform -> restringere niche solo lì

---

## 2026-06-13 — DATI REALI (primo accesso analytics)

### Numeri brutali
- **48 video pubblicati | 155 view totali | 1 iscritto | 0 like assoluti**
- Media 3 view/video. Engagement zero = algoritmo non spinge.

### Top performer (cosa la gente clicca)
- 21 view: roller coaster uccide 3 persone (shock/disastro)
- 7 view: 14 auto scomparse da una gara (mistero)
- 5 view: Hannibal distrugge esercito romano / medaglia canadese

### Problema #1 — titoli identici
TUTTI iniziano "Il giorno in cui..." = sembrano lo stesso video = CTR zero.
FIX: vietato "Il giorno in cui", titoli variati obbligatori.

### Problema #2 — bias storia
Pipeline pescava da Wikipedia "accadde oggi" = sempre storia oscura.
Cherokee, Oda Nobunaga, Louisbourg = nessuno cerca, nessuno capisce senza contesto.
FIX: ridotto peso storia (5->3), aggiunte fonti ScienceDaily strange+animali.

### Insight
Vince SHOCK/MISTERO senza prerequisiti (roller coaster, auto sparite, polpo).
Perde storia che richiede contesto. -> Niche su scienza/natura/misteri "wow".

### Decisioni applicate
- Priorita topic: scienza/natura > misteri > (storia solo se nulla di meglio)
- Titoli: vietato pattern ripetitivo
- Fonti dati ribilanciate verso scienza bizzarra + animali
