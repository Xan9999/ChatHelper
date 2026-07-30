# Per-collection widget text overrides

Drop a file named `<collection>.json` here (same name as `client_id` in that
site's embed snippet, e.g. `ricambiribi.json`) to customize the widget's UI
text for that site — any subset of these keys:

```json
{
  "title": "Ricambi Ribi",
  "subtitle": "Chiedi dei ricambi per il tuo mezzo",
  "placeholder": "Scrivi qui la tua domanda...",
  "send": "Invia",
  "unreachable": "Assistente non raggiungibile al momento."
}
```

Served at `GET /widget-strings.json?client_id=<collection>` and merged
client-side over the plain language defaults (`en`/`it`/`sl`, chosen by the
`language` param in the embed snippet) — a collection with no file here, or
a file missing some keys, just keeps the language default for whatever isn't
overridden. Nothing to configure for sites that don't need custom wording.

This is independent of `../widget_styles/` (visual CSS) — use either, both,
or neither per site.
