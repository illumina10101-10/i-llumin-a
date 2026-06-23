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
- [ ] Re-auth YouTube con scope readonly per leggere analytics reali
- [ ] Dopo 7 giorni: confronto retention vecchio vs nuovo formato
- [ ] Se natura/animali outperform -> restringere niche solo lì
