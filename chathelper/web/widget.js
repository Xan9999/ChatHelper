/* ChatHelper — self-injecting chat widget.
 * Loaded via a single async <script> tag (see README "Customizing the widget"):
 *   <script>
 *   !function(d,u,i,l,p,a){
 *       var s=d.createElement("script");s.async=1;
 *       s.src=u+"?client_id="+i+"&language="+l+(p?"&position="+p:"")+(a?"&accent="+encodeURIComponent(a):"");
 *       var h=d.getElementsByTagName("script")[0];h.parentNode.insertBefore(s,h);
 *   }(document,"https://your-backend/widget.js","your-client-id","en");
 *   </script>
 * client_id selects which site's knowledge base to use (it's the Qdrant
 * collection name from `chathelper ingest --collection <client_id>`).
 * language only picks the widget's UI strings below — the assistant itself
 * already answers in whatever language the visitor types in.
 *
 * Optional visual params — pass as the 5th (position) and/or 6th (accent)
 * argument to the wrapper function above, e.g.:
 *   }(document,"https://your-backend/widget.js","your-client-id","en","left","#f17023");
 * so one shared widget.js file can look different per site without
 * maintaining multiple copies. They end up as query params on THIS script's
 * own src (read below via document.currentScript), which is what actually
 * matters if you ever build the src by some other means than the wrapper:
 *   accent   — hex color for the header/buttons/user bubbles, e.g. &accent=%23f17023
 *              for #f17023 (the wrapper above URL-encodes it for you). Falls
 *              back to the default blue if missing or malformed.
 *   position — "left" or "right" (default "right"): which bottom corner the
 *              toggle button and panel open from.
 *
 * For anything beyond a color and a corner (fonts, spacing, animations, a
 * logo, dark mode...), drop a full CSS file at
 * <WIDGET_STYLES_DIR>/<client_id>.css on the backend — it's served at
 * GET /widget.css?client_id=... and linked here automatically, no widget.js
 * changes needed. Same idea for the UI TEXT (title/subtitle/placeholder/
 * send/unreachable message): drop <WIDGET_STRINGS_DIR>/<client_id>.json
 * (any subset of those keys) — served at GET /widget-strings.json?client_id=...
 * and merged over the language defaults below. See README "Customizing the widget".
 */
(function () {
  "use strict";

  // Every id, class and CSS variable the widget creates carries the
  // "chathelper-" prefix: it keeps host-site styles from colliding with the
  // widget and is the public hook for per-site overrides (widget_styles/*.css).
  var thisScript = document.currentScript ||
    (function () { var s = document.getElementsByTagName("script"); return s[s.length - 1]; })();
  var scriptUrl = new URL(thisScript.src, window.location.href);
  var BACKEND = scriptUrl.origin;
  var CLIENT_ID = scriptUrl.searchParams.get("client_id") || "";
  var LANG = (scriptUrl.searchParams.get("language") || "en").toLowerCase();
  var ACCENT = scriptUrl.searchParams.get("accent") || "";
  if (ACCENT && !/^#[0-9a-fA-F]{3,8}$/.test(ACCENT)) ACCENT = ""; // malformed -> keep default
  var SIDE = (scriptUrl.searchParams.get("position") || "right").toLowerCase() === "left" ? "left" : "right";

  var STRINGS = {
    en: { title: "Assistant", subtitle: "Ask about this site", placeholder: "Type your question...",
          send: "Send", unreachable: "Could not reach the assistant. Is the backend running?" },
    it: { title: "Assistente", subtitle: "Chiedi informazioni su questo sito", placeholder: "Scrivi la tua domanda...",
          send: "Invia", unreachable: "Impossibile contattare l'assistente. Il servizio è attivo?" },
    sl: { title: "Pomočnik", subtitle: "Vprašaj o tej spletni strani", placeholder: "Vnesite vprašanje...",
          send: "Pošlji", unreachable: "Pomočnika ni mogoče doseči. Ali strežnik deluje?" },
  };
  // Copy (not reference) STRINGS[LANG] — a per-collection override merges
  // INTO this object later, and must not mutate the shared language defaults.
  var t = Object.assign({}, STRINGS[LANG] || STRINGS.en);

  var css = ""
    + ":root{--chathelper-accent:#3b5bdb;--chathelper-bg:#fff;--chathelper-fg:#1a1a2e;--chathelper-muted:#6b7280;--chathelper-panel:#f7f8fa;}"
    + (ACCENT ? ":root{--chathelper-accent:" + ACCENT + ";}" : "")
    + "#chathelper-toggle{position:fixed;bottom:24px;" + SIDE + ":24px;width:60px;height:60px;border-radius:50%;"
    + "background:var(--chathelper-accent);color:#fff;border:none;font-size:26px;cursor:pointer;"
    + "box-shadow:0 6px 20px rgba(0,0,0,.25);z-index:999999;font-family:system-ui,sans-serif;}"
    + "#chathelper-panel{position:fixed;bottom:96px;" + SIDE + ":24px;width:380px;max-width:calc(100vw - 32px);"
    + "height:560px;max-height:calc(100vh - 120px);background:var(--chathelper-bg);border-radius:16px;"
    + "box-shadow:0 12px 40px rgba(0,0,0,.28);display:none;flex-direction:column;overflow:hidden;"
    + "z-index:999999;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--chathelper-fg);}"
    + "#chathelper-panel.open{display:flex;}"
    + "#chathelper-panel .chathelper-hdr{background:var(--chathelper-accent);color:#fff;padding:14px 16px;font-weight:600;}"
    + "#chathelper-panel .chathelper-hdr small{display:block;font-weight:400;opacity:.85;font-size:12px;}"
    + "#chathelper-panel .chathelper-msgs{flex:1;overflow-y:auto;padding:16px;background:var(--chathelper-panel);}"
    + "#chathelper-panel .chathelper-msg{margin-bottom:14px;display:flex;}"
    + "#chathelper-panel .chathelper-msg .chathelper-bubble{padding:10px 13px;border-radius:14px;max-width:82%;"
    + "line-height:1.45;white-space:pre-wrap;word-wrap:break-word;}"
    + "#chathelper-panel .chathelper-msg.user{justify-content:flex-end;}"
    + "#chathelper-panel .chathelper-msg.user .chathelper-bubble{background:var(--chathelper-accent);color:#fff;border-bottom-right-radius:4px;}"
    + "#chathelper-panel .chathelper-msg.bot .chathelper-bubble{background:#fff;border:1px solid #e5e7eb;border-bottom-left-radius:4px;}"
    + "#chathelper-panel .chathelper-msg.bot .chathelper-bubble a{color:var(--chathelper-accent);text-decoration:underline;word-break:break-all;}"
    + "#chathelper-panel .chathelper-sources{font-size:11px;color:var(--chathelper-muted);margin-top:6px;}"
    + "#chathelper-panel .chathelper-sources a{color:var(--chathelper-accent);text-decoration:none;}"
    + "#chathelper-panel .chathelper-composer{display:flex;border-top:1px solid #e5e7eb;padding:10px;gap:8px;background:#fff;}"
    + "#chathelper-panel .chathelper-composer input{flex:1;border:1px solid #d1d5db;border-radius:10px;padding:10px 12px;"
    + "font-size:14px;outline:none;}"
    + "#chathelper-panel .chathelper-composer button{background:var(--chathelper-accent);color:#fff;border:none;border-radius:10px;"
    + "padding:0 16px;cursor:pointer;font-size:14px;}"
    + "#chathelper-panel .chathelper-composer button:disabled{opacity:.5;cursor:default;}";
  var styleEl = document.createElement("style");
  styleEl.textContent = css;
  document.head.appendChild(styleEl);

  // Optional per-collection CSS override (full, arbitrary CSS — fonts,
  // spacing, dark mode, anything) — a plain <link>, loaded AFTER the base
  // <style> above so its rules win the cascade on equal specificity. A
  // collection with no override file gets back an empty (but valid)
  // stylesheet from the backend, so this is a safe no-op by default.
  var linkEl = document.createElement("link");
  linkEl.rel = "stylesheet";
  linkEl.href = BACKEND + "/widget.css?client_id=" + encodeURIComponent(CLIENT_ID);
  document.head.appendChild(linkEl);

  var toggle = document.createElement("button");
  toggle.id = "chathelper-toggle";
  toggle.title = "Chat";
  toggle.textContent = "💬"; // 💬

  var panel = document.createElement("div");
  panel.id = "chathelper-panel";
  panel.innerHTML =
    '<div class="chathelper-hdr">' + t.title + '<small>' + t.subtitle + '</small></div>'
    + '<div class="chathelper-msgs"></div>'
    + '<form class="chathelper-composer">'
    + '<input autocomplete="off" placeholder="' + t.placeholder + '" />'
    + '<button type="submit">' + t.send + '</button>'
    + '</form>';

  document.body.appendChild(toggle);
  document.body.appendChild(panel);

  var els = {
    msgs: panel.querySelector(".chathelper-msgs"),
    form: panel.querySelector(".chathelper-composer"),
    input: panel.querySelector("input"),
    send: panel.querySelector("button"),
  };
  // Optional per-collection text override (title/subtitle/placeholder/send/
  // unreachable) — fetched async so it never delays the widget's first
  // paint; applies moments later if a collection has an override file, same
  // timing model as the CSS <link> above. Uses textContent/nodeValue (never
  // innerHTML) to apply it, even though the source is operator-trusted.
  fetch(BACKEND + "/widget-strings.json?client_id=" + encodeURIComponent(CLIENT_ID))
    .then(function (r) { return r.json(); })
    .then(function (overrides) {
      if (!overrides || typeof overrides !== "object") return;
      Object.assign(t, overrides);
      var hdr = panel.querySelector(".chathelper-hdr");
      if (overrides.title) hdr.childNodes[0].nodeValue = t.title;
      if (overrides.subtitle) hdr.querySelector("small").textContent = t.subtitle;
      if (overrides.placeholder) els.input.placeholder = t.placeholder;
      if (overrides.send) els.send.textContent = t.send;
      // t.unreachable needs no DOM patch — read live from `t` in the
      // .catch() handler further down, whenever it's actually needed.
    })
    .catch(function () {}); // no override file / network hiccup -> keep defaults

  var history = [];
  var conversationId = window.crypto && window.crypto.randomUUID
    ? window.crypto.randomUUID()
    : "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
        var r = Math.floor(Math.random() * 16);
        return (c === "x" ? r : (r & 3 | 8)).toString(16);
      });

  toggle.onclick = function () { panel.classList.toggle("open"); };

  function addMsg(role, text) {
    var wrap = document.createElement("div");
    wrap.className = "chathelper-msg " + role;
    var bubble = document.createElement("div");
    bubble.className = "chathelper-bubble";
    bubble.textContent = text;
    wrap.appendChild(bubble);
    els.msgs.appendChild(wrap);
    els.msgs.scrollTop = els.msgs.scrollHeight;
    return bubble;
  }

  function escapeHtml(s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;")
            .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function stripSourcesLine(s) {
    return s.replace(/[\s\n]*(?:Sources|Viri|Fonti)\s*:?\s*(?:\[\d+\][\s,;]*)+[\s.]*$/i, "");
  }

  function renderMessage(raw) {
    var text = stripSourcesLine(raw);
    var linkRe = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|<(https?:\/\/[^>\s]+)>|(https?:\/\/[^\s<>"')\]]+)/g;
    var parts = [];
    var last = 0, m;
    while ((m = linkRe.exec(text)) !== null) {
      parts.push(escapeHtml(text.slice(last, m.index)));
      var label, url, trailing = "";
      if (m[1]) { label = m[1]; url = m[2]; }
      else { url = m[3] || m[4]; label = url; }
      var punct = url.match(/[.,;:!?]+$/);
      if (punct) { trailing = punct[0]; url = url.slice(0, -trailing.length); if (!m[1]) label = url; }
      parts.push('<a href="' + escapeHtml(url) + '" target="_blank" rel="noopener">'
                 + escapeHtml(label) + '</a>' + escapeHtml(trailing));
      last = m.index + m[0].length;
    }
    parts.push(escapeHtml(text.slice(last)));
    // Runs on already-escaped text, so it can only produce the <strong> tag itself.
    return parts.join("").replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  }

  function currentPage() {
    return {
      url: location.href,
      title: document.title,
      text: (document.body.innerText || "").slice(0, 4000),
    };
  }

  function renderSources(bubble, sources) {
    var valid = (sources || []).filter(function (s) {
      if (!s || typeof s.url !== "string") return false;
      try {
        var parsed = new URL(s.url);
        return parsed.protocol === "http:" || parsed.protocol === "https:";
      } catch (_) {
        return false;
      }
    });
    if (!valid.length) return;
    var div = document.createElement("div");
    div.className = "chathelper-sources";
    div.appendChild(document.createTextNode("Sources: "));
    valid.forEach(function (s, index) {
      if (index) div.appendChild(document.createTextNode(" "));
      var link = document.createElement("a");
      link.href = s.url;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = "[" + String(s.n) + "]";
      div.appendChild(link);
    });
    bubble.parentElement.appendChild(div);
  }

  els.form.onsubmit = function (e) {
    e.preventDefault();
    var message = els.input.value.trim();
    if (!message) return;
    els.input.value = "";
    els.send.disabled = true;
    addMsg("user", message);

    var bubble = addMsg("bot", "");
    var answer = "";

    fetch(BACKEND + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: message, history: history, current_page: currentPage(),
        conversation_id: conversationId, client_id: CLIENT_ID,
      }),
    }).then(function (resp) {
      if (!resp.ok) {
        return resp.json().catch(function () { return {}; }).then(function (data) {
          throw new Error(data.detail || t.unreachable);
        });
      }
      var reader = resp.body.getReader();
      var decoder = new TextDecoder();
      var buffer = "";
      function pump() {
        return reader.read().then(function (r) {
          if (r.done) return;
          buffer += decoder.decode(r.value, { stream: true });
          var parts = buffer.split("\n\n");
          buffer = parts.pop();
          parts.forEach(function (part) {
            var line = part.replace(/^data: /, "").trim();
            if (!line) return;
            var evt = JSON.parse(line);
            if (evt.type === "token") { answer += evt.text; bubble.innerHTML = renderMessage(answer); }
            else if (evt.type === "sources") { renderSources(bubble, evt.sources); }
            else if (evt.type === "error") { bubble.textContent = "⚠️ " + evt.message; }
            els.msgs.scrollTop = els.msgs.scrollHeight;
          });
          return pump();
        });
      }
      return pump();
    }).then(function () {
      history.push({ role: "user", content: message });
      history.push({ role: "assistant", content: answer });
    }).catch(function (error) {
      bubble.textContent = error.message || t.unreachable;
    }).finally(function () {
      els.send.disabled = false;
      els.input.focus();
    });
  };
})();
