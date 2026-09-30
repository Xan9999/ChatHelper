# Per-collection widget CSS overrides

Drop a file named `<collection>.css` here (the same name used as `client_id`
in that site's embed snippet, e.g. `ricambiribi.css`) to fully customize the
chat widget's look for that site — any CSS is allowed: fonts, spacing,
animations, a logo via `background-image`, dark mode, anything.

It's served at `GET /widget.css?client_id=<collection>` and linked by
`widget.js` automatically, right after the widget's own base styles, so your
rules win the cascade without `!important`. A collection with no file here
just gets the default look — nothing to configure for sites that don't need
customizing.

Useful hooks already in the base markup (see `chathelper/web/widget.js`
for the full structure): `#wah-toggle` (the floating button), `#wah-panel`
(the chat window), `.wah-hdr`, `.wah-msgs`, `.wah-msg.user`/`.wah-msg.bot`
bubbles, `.wah-composer`. The base stylesheet also defines CSS custom
properties (`--wah-accent`, `--wah-bg`, `--wah-fg`, `--wah-muted`,
`--wah-panel`) you can simply reassign instead of rewriting whole rules:

```css
/* ricambiribi.css */
:root { --wah-accent: #d4321c; }
#wah-panel { font-family: "Segoe UI", sans-serif; border-radius: 4px; }
#wah-toggle { background-image: url(https://ricambiribi.com/wp-content/uploads/logo-icon.png); }
```

For a one-line color/position tweak with no file at all, the `accent` and
`position` query params on the widget.js snippet itself are simpler — see
README "Embedding the widget". This directory is for anything beyond that.
