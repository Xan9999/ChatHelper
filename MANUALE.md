# Manuale d'uso — Assistente Virtuale per il Sito Web

Questa guida spiega, in modo semplice, cos'è l'assistente virtuale (chatbot)
installato sul vostro sito, cosa sa fare, come inserirlo, e come consultare le
conversazioni dei visitatori. Non è richiesta alcuna conoscenza tecnica.

> Per l'installazione, la configurazione dei server e gli aspetti tecnici,
> fare riferimento alla documentazione tecnica (`README.md`) oppure contattare
> chi vi ha fornito il servizio.

---

## Indice

1. [Cos'è l'assistente virtuale](#1-cosè-lassistente-virtuale)
2. [Cosa sa fare (e cosa non sa fare)](#2-cosa-sa-fare-e-cosa-non-sa-fare)
3. [Come lo vedono i vostri visitatori](#3-come-lo-vedono-i-vostri-visitatori)
4. [Come inserirlo sul vostro sito](#4-come-inserirlo-sul-vostro-sito)
5. [Avviare i servizi](#5-avviare-i-servizi)
6. [Scansionare un sito web (comando `ingest`)](#6-scansionare-un-sito-web-comando-ingest)
7. [Avviare l'assistente (comando `serve`)](#7-avviare-lassistente-comando-serve)
8. [Preparazione iniziale (comando `init`)](#8-preparazione-iniziale-comando-init)
9. [Tenere aggiornati i contenuti](#9-tenere-aggiornati-i-contenuti)
10. [Consultare le conversazioni dei visitatori](#10-consultare-le-conversazioni-dei-visitatori)
11. [Domande frequenti](#11-domande-frequenti)
12. [Assistenza](#12-assistenza)
13. [Riferimento completo dei comandi](#13-riferimento-completo-dei-comandi)

---

## 1. Cos'è l'assistente virtuale

È una piccola finestra di chat che appare sul vostro sito web (di solito in
basso a destra) e risponde alle domande dei visitatori, 24 ore su 24, come un
addetto che conosce a memoria tutto il vostro sito.

Per rispondere, l'assistente si basa su due fonti, nell'ordine in cui vi si
può fidare di più:

1. **La pagina che il visitatore sta guardando** in quel momento.
2. **I contenuti del vostro sito** — testi delle pagine, schede prodotto,
   PDF collegati (listini, brochure) — raccolti in anticipo e usati come base
   di conoscenza generale.

Tutto funziona in locale o tramite fornitori scelti da voi: nessun dato viene
condiviso con terzi senza il vostro controllo.

## 2. Cosa sa fare (e cosa non sa fare)

**Sa fare:**
- Rispondere a domande sui prodotti, servizi, orari, prezzi pubblicati,
  politiche del sito, come contattarvi, ecc.
- Capire la domanda in qualsiasi lingua scriva il visitatore, e rispondere
  nella stessa lingua.
- Suggerire e collegare la pagina giusta del sito quando è utile (link
  cliccabili nella risposta).
- Tenere conto di cosa il visitatore sta guardando in quel momento, per
  risposte più pertinenti ("questa pagina", "questo prodotto").

**Non sa fare (per scelta, a garanzia della qualità):**
- Non inventa mai prezzi, disponibilità o informazioni che non trova — se non
  sa rispondere, lo dice apertamente e suggerisce dove cercare.
- Non esegue azioni al posto del visitatore: non effettua acquisti e non
  consulta o modifica ordini.
- Non sostituisce l'assistenza clienti per casi complessi o delicati — resta
  comunque un buon primo filtro per le domande più comuni.

## 3. Come lo vedono i vostri visitatori

Il visitatore clicca sul pulsante della chat, scrive una domanda in linguaggio
naturale (come se scrivesse a una persona) e riceve una risposta in pochi
secondi, scritta progressivamente (come se qualcuno la stesse digitando in
diretta). Se la risposta si basa sui contenuti del sito, accanto compaiono dei
riferimenti numerati che rimandano alle pagine di origine.

## 4. Come inserirlo sul vostro sito

Per ogni sito viene fornito un piccolo codice da incollare **una sola volta**,
di solito nel footer (il fondo di ogni pagina), simile a questo:

```html
<script>
!function(d,u,i,l){
    var s=d.createElement("script");s.async=1;s.src=u+"?client_id="+i+"&language="+l;
    var h=d.getElementsByTagName("script")[0];h.parentNode.insertBefore(s,h);
}(document,"https://srv.tallweb.eu/widget.js","vostro-codice-sito","it");
</script>
```

Non serve capire il funzionamento interno — bastano tre informazioni, che vi
verranno fornite già pronte:

- **`https://srv.tallweb.eu/widget.js`**: l'indirizzo del widget. Deve
  terminare con `/widget.js`: il solo nome del server non basta e il browser
  segnalerebbe un errore di tipo MIME.
- **`vostro-codice-sito`**: un identificativo che dice all'assistente quali
  contenuti usare per rispondere (ogni sito ha il proprio).
- **`"it"`**: la lingua dei testi del widget stesso (pulsanti, messaggio di
  benvenuto) — l'assistente risponderà comunque sempre nella lingua in cui
  scrive il visitatore, indipendentemente da questo valore.

**Su WordPress**, il modo più semplice è incollare il codice tramite un plugin
"header/footer" (ad esempio *WPCode* o *Insert Headers and Footers*),
scegliendo "applica a tutte le pagine" — così va inserito una sola volta e
compare automaticamente ovunque, senza bisogno di modificare pagina per
pagina.

Se preferite personalizzare l'aspetto grafico del pulsante e della finestra di
chat, è disponibile anche una versione "manuale" del widget — chiedete al
vostro fornitore.

**Colori, testi e tono di voce personalizzati per sito.** Se gestite più siti
con lo stesso assistente, ognuno può avere un aspetto ed espressione
completamente diversi, senza mai duplicare il widget:
- **Colori e aspetto grafico** — dal semplice colore del pulsante fino a
  font, animazioni, un logo personalizzato o una grafica scura, per abbinarsi
  al brand di ogni sito.
- **Testi del widget** — il titolo, il messaggio di benvenuto, il testo del
  pulsante di invio, possono essere riscritti per ogni sito (ad esempio il
  titolo può diventare il nome della vostra azienda invece del generico
  "Assistente").
- **Tono di voce delle risposte** — più formale su un sito, più amichevole e
  informale su un altro.

Basta chiedere a chi gestisce il servizio: sono tutte piccole impostazioni,
non richiedono di ricreare il widget da zero.

## 5. Avviare i servizi

L'assistente usa diversi servizi che devono restare attivi. Nella versione
pubblicata sul server Linux vengono avviati e mantenuti da Docker Compose;
non serve aprire un terminale separato per ciascuno:

| Motore | A cosa serve, in parole semplici |
|---|---|
| **Qdrant** | È il "magazzino" dove restano conservati i contenuti del sito già letti — uno scaffale separato per ogni sito gestito. |
| **Embeddings** | È il motore che sa "cercare per significato": lo usa sia quando si legge un nuovo sito, sia ogni volta che un visitatore fa una domanda, per trovare le informazioni giuste. |
| **LLM (modello di chat)** | È il motore che scrive davvero le risposte — il "cervello" che compone il testo che il visitatore legge. Nella configurazione standard è il servizio ChatGPT di OpenAI (le domande e il testo della pagina visitata vengono quindi inviati a OpenAI); in alternativa può essere un modello installato sul vostro server. |
| **PostgreSQL** | Conserva le conversazioni per la consultazione privata; non contiene cataloghi prodotti o ordini. |
| **ChatHelper** | Riceve le domande dal widget e coordina gli altri servizi. |
| **Caddy** | Offre l'indirizzo HTTPS pubblico e inoltra le richieste a ChatHelper. |

Chi gestisce il server può verificarne lo stato dalla cartella del progetto:

```bash
bash scripts/deploy.sh status
```

La procedura di avvio e manutenzione è in `DEPLOYMENT.md`. Gli script
`start-*.ps1` e `start-*.sh` servono solo per prove locali senza Docker.

## 6. Scansionare un sito web (comando `ingest`)

Prima che l'assistente possa rispondere sui contenuti di un sito, il sito va
"letto" una volta con il comando `ingest`. Esempio minimo:

```bash
chathelper ingest https://www.vostrosito.it --collection vostrosito
```

Cosa fa: apre l'indirizzo indicato, segue via via i link interni del sito
pagina dopo pagina, scarica anche i PDF collegati (ad esempio listini o
brochure), e alla fine memorizza tutto sotto il nome scelto (qui
`vostrosito`) — lo stesso nome che comparirà nello snippet del widget (sezione
4) e nella pagina di revisione delle conversazioni (sezione 10).
Nel deployment Docker si usa `bash scripts/deploy.sh ingest` seguito dagli
stessi argomenti, dopo che lo stack è stato avviato.

Opzioni disponibili, da aggiungere dopo l'indirizzo del sito:

| Opzione | A cosa serve |
|---|---|
| `--collection NOME` | Il nome con cui salvare questo sito. Obbligatorio se si gestisce più di un sito, per non mescolare i contenuti di siti diversi. |
| `--max-pages N` | Quante pagine leggere al massimo — utile per limitare siti molto grandi, oppure per fare una prova veloce su poche pagine. |
| `--all-domains` | Normalmente la lettura resta all'interno del sito di partenza; con questa opzione segue i link anche verso altri siti collegati. |
| `--render` | Da usare se il sito costruisce i contenuti con JavaScript (ad esempio applicazioni "a pagina singola" moderne): fa "vedere" ogni pagina come farebbe un browser, così legge anche il testo che compare solo dopo il caricamento. Richiede un piccolo componente aggiuntivo installato una tantum (chiedere assistenza se serve). |
| `--site-name "Nome"` | Il nome con cui l'assistente si presenta nelle risposte (ad esempio "assistente di Nome"). |
| `--replace` | Svuota e ricrea da zero lo "scaffale" del sito, ma solo dopo che la nuova scansione è riuscita (vedi sotto). |

Il significato dettagliato di ogni opzione, con i valori predefiniti, è nella
sezione 13.

Rilanciare la scansione di un sito già letto è sicuro: le pagine rilette
sostituiscono la propria versione precedente, senza creare duplicati. Le
pagine che nel frattempo sono state eliminate dal sito restano però in
memoria finché non si fa una scansione "da zero", che svuota e ricrea lo
scaffale del sito solo dopo che la nuova lettura è andata a buon fine:

```bash
chathelper ingest https://www.vostrosito.it --collection vostrosito --replace
```

(`--replace` va aggiunto anche quando si usa `bash scripts/deploy.sh ingest`).

## 7. Avviare l'assistente (comando `serve`)

Per prove locali, una volta letto almeno un sito e avviato PostgreSQL, questo
comando accende l'API dell'assistente:

```bash
chathelper serve --collection vostrosito
```

Opzioni disponibili:

| Opzione | A cosa serve |
|---|---|
| `--collection NOME` | Quale sito servire — deve corrispondere al nome usato con `ingest`. |
| `--site-name "Nome"` | Come sopra: il nome con cui l'assistente si presenta. |
| `--host` | Chi può collegarsi al servizio: il valore predefinito (`127.0.0.1`) significa "solo questo stesso computer". Nel deployment Docker l'indirizzo interno è configurato in Compose e solo Caddy è pubblico. |
| `--port NUMERO` | Il "canale" numerico su cui il servizio risponde (8000 di default). Va cambiato solo se quel numero è già occupato da qualcos'altro sullo stesso computer. |
| `--ssl-certfile` / `--ssl-keyfile` | Per far parlare l'assistente direttamente in connessione sicura (HTTPS), indicando i due file del certificato. Non necessario se davanti c'è già un altro sistema che se ne occupa (soluzione comune nelle installazioni più curate). |

Una sola installazione può servire **più siti insieme**: ogni sito ha la
propria collezione Qdrant e lo snippet del widget invia il relativo
`client_id`. Non è necessario avviare un processo separato per sito.

## 8. Preparazione iniziale (comando `init`)

Solo per una prova locale, la primissima volta che si configura
l'applicazione su un nuovo computer, questo comando

```bash
chathelper init
```

crea un file `.env` di base nella cartella del progetto, da compilare
con le informazioni necessarie (dove si trovano i tre motori della sezione 5,
quale modello usare, e così via). Questo passaggio — come la scelta e
l'installazione dei modelli stessi — viene normalmente svolto una sola volta
da chi installa il servizio: non fa parte dell'uso quotidiano. Nel deployment
Docker si usa invece `bash scripts/deploy.sh prepare` e `.env.production`.

## 9. Tenere aggiornati i contenuti

L'assistente impara i contenuti del sito tramite la scansione descritta nella
sezione 6: se aggiungete nuove pagine, prodotti o modificate testi importanti,
l'assistente li conoscerà a partire dalla prossima scansione. Se gestite voi
stessi il servizio, potete rilanciare il comando `ingest` quando i contenuti
cambiano in modo sostanziale; se invece il servizio è gestito da qualcun
altro per conto vostro, segnalate le modifiche importanti per richiedere un
aggiornamento anticipato.

Le informazioni che cambiano spesso, come prezzi e disponibilità, sono
affidabili solo quanto l'ultima scansione oppure il testo della pagina che il
visitatore sta guardando. Dopo cambiamenti importanti conviene quindi
rilanciare `ingest`.

## 10. Consultare le conversazioni dei visitatori

Ogni conversazione viene registrata automaticamente, così potete verificare
cosa chiedono i visitatori e come risponde l'assistente. La consultazione
avviene tramite un indirizzo web privato, protetto da un codice di accesso
personale (fornito da chi gestisce il servizio) — senza quel codice, nessuno
può leggere le conversazioni.

L'indirizzo ha questa forma:

```
https://vostro-indirizzo/qa/login
```

Cosa si trova:

- **L'elenco generale** mostra tutte le conversazioni: quando sono iniziate,
  quanti messaggi contengono, quanto sono durate, e un'anteprima della prima
  domanda del visitatore.
- Se gestite **più siti** con lo stesso servizio (ognuno avviato come nella
  sezione 7), in alto trovate un elenco di collegamenti (uno per sito) per
  vedere solo le conversazioni di un sito alla volta — ad esempio aggiungendo
  il codice del sito in fondo all'indirizzo: `.../qa/vostro-codice-sito`
- Cliccando su una conversazione (**view**) si apre la trascrizione completa,
  leggibile come un dialogo (visitatore / assistente), con i tempi di risposta.
  È disponibile anche **txt** per scaricarla come semplice file di testo.

Questo strumento è pensato per **controllo qualità**: verificare che le
risposte siano corrette, individuare domande a cui l'assistente non ha saputo
rispondere bene (segno che forse manca un contenuto sul sito), e capire cosa
interessa davvero ai vostri visitatori.

## 11. Domande frequenti

**Perché a volte l'assistente risponde solo con un link, invece di darmi
subito l'informazione?**
Succede raramente: l'assistente è impostato per dare sempre prima la risposta
concreta (date, prezzi, orari) se la trova nei contenuti, aggiungendo il link
solo come approfondimento. Se notate risposte che rimandano soltanto a una
pagina senza spiegare nulla, segnalatelo: probabilmente quel contenuto non è
ancora ben coperto dal sito, oppure serve un piccolo aggiustamento.

**Uno dei servizi (sezione 5) si è bloccato — devo reinstallare tutto?**
No: nella versione pubblicata sul server i servizi vengono riavviati
automaticamente; in una prova locale basta richiudere quel comando e
rilanciarlo. Se il problema si ripete spesso, segnalatelo a chi gestisce il
servizio.

**L'assistente può sbagliare o inventare cose?**
È stato impostato per non inventare mai fatti, prezzi o disponibilità: se non
trova l'informazione, lo dichiara e suggerisce dove cercare altrove. Come ogni
sistema automatico, può però capitare raramente qualche risposta imprecisa o
poco chiara — per questo è utile controllare periodicamente le conversazioni
(vedi sezione 10).

**Posso vedere cosa chiedono i visitatori?**
Sì, tramite la pagina privata di consultazione descritta nella sezione 10.

**Il widget non compare, oppure mostra un errore di connessione — cosa
faccio?**
Non è qualcosa che dovete risolvere direttamente: segnalatelo a chi gestisce
il servizio, indicando su quale pagina è successo e, se possibile, un
messaggio di errore o uno screenshot.

**Voglio aggiungere l'assistente a un altro sito che gestisco — cosa serve?**
Basta chiedere: ogni sito nuovo riceve il proprio codice identificativo e
richiede solo di incollare lo stesso tipo di snippet visto nella sezione 4,
con quel nuovo codice.

**Le conversazioni dei visitatori sono al sicuro?**
Sono conservate privatamente e consultabili solo tramite il codice di accesso
personale. Chi gestisce il servizio può impostare un periodo di conservazione
(ad esempio 90 giorni), dopo il quale le conversazioni vengono cancellate
automaticamente. Se il "cervello" (modello di chat) è un servizio esterno
anziché un server vostro, le domande dei visitatori e il testo della pagina
che stanno guardando vengono inviati a quel fornitore: va indicato
nell'informativa privacy del sito.

## 12. Assistenza

Per qualsiasi domanda su installazione, aggiornamenti dei contenuti, nuovi
siti da collegare, o problemi tecnici, contattate chi vi ha fornito il
servizio.

## 13. Riferimento completo dei comandi

Questa sezione è per chi gestisce il servizio. Elenca ogni comando del
programma `chathelper`, tutte le sue opzioni e i valori usati quando
un'opzione viene omessa. Ogni comando accetta `-h` (o `--help`) e stampa
l'elenco delle proprie opzioni.

**Dove e come si lanciano.** I comandi leggono la configurazione dal file
`.env` della cartella in cui vengono eseguiti. Sul server di produzione
(`srv.tallweb.eu`) il programma è `/srv/chathelper/venv/bin/chathelper`, la
cartella è `/srv/chathelper/app` e il comando va eseguito come utente
`chathelper`, cioè:

```bash
runuser -u chathelper -- bash -c 'cd /srv/chathelper/app && /srv/chathelper/venv/bin/chathelper <comando> <opzioni>'
```

Su un computer di prova, dopo `setup.sh`/`setup.ps1` e l'attivazione
dell'ambiente virtuale, basta `chathelper <comando> <opzioni>`.

### 13.1 `chathelper ingest` — leggere o rileggere un sito

Sintassi: `chathelper ingest URL [opzioni]`

| Argomento / opzione | Cosa fa | Se omesso |
|---|---|---|
| `URL` (obbligatorio) | Indirizzo da cui parte la lettura, ad esempio `https://www.vostrosito.it`. La lettura segue i link interni partendo da qui; conviene indicare la home page. | — |
| `--collection NOME` | Nome dello "scaffale" (collezione) in cui salvare il sito. È lo stesso valore da usare come `client_id` nello snippet del widget. Ammessi lettere, cifre, `-` e `_`. | Il valore di `QDRANT_COLLECTION` nel file `.env` (sul server: `tallweb`). Con più siti va sempre indicato. |
| `--max-pages N` | Numero massimo di pagine (HTML e PDF) lette in questa esecuzione. Raggiunto il limite la lettura si ferma anche se restano link da seguire. | `CRAWL_MAX_PAGES` del `.env` (sul server: 200). |
| `--all-domains` | Segue anche i link verso altri domini. Da usare solo se i contenuti del sito sono distribuiti su più domini: altrimenti la lettura esce dal sito e spreca il budget di pagine. | Resta sul dominio di partenza; `www.sito.it` e `sito.it` contano come lo stesso sito. |
| `--render` | Apre ogni pagina in un browser invisibile (Chromium) ed esegue il JavaScript prima di leggerla: serve per i siti che costruiscono i contenuti via script. Più lento. Richiede, una tantum, `pip install "chathelper[render]"` e `playwright install chromium`. Il tempo di attesa per pagina è `CRAWL_RENDER_WAIT_MS` (5000 ms). | Lettura semplice del codice HTML, senza eseguire script. |
| `--site-name "Nome"` | Nome del sito usato nei messaggi di questa esecuzione. In produzione, con più siti, il nome usato nelle risposte viene da `SITE_NAMES` nel `.env` (`collezione=Nome,...`), non da questa opzione. | `SITE_NAME` del `.env`. |
| `--replace` | Dopo una scansione **riuscita**, svuota la collezione e la ricrea con i soli contenuti appena letti: elimina le pagine che non esistono più sul sito. Se la scansione non trova nulla, il comando si ferma senza toccare la collezione esistente. | Le pagine rilette sostituiscono la propria versione precedente; le pagine sparite dal sito restano in memoria. |

Cosa succede, in ordine, quando si lancia `ingest`:

1. Verifica che Qdrant e il servizio di embedding rispondano; se uno dei due
   è irraggiungibile si ferma subito, prima di iniziare a leggere.
2. Legge il sito pagina per pagina. Vengono saltati automaticamente: i file
   binari (immagini, archivi, video, font, documenti Office), le pagine più
   grandi di `CRAWL_MAX_PAGE_MB` (5 MB), i PDF più grandi di
   `CRAWL_PDF_MAX_MB` (20 MB) e i PDF senza testo (scansioni). I PDF vengono
   letti solo se `CRAWL_PDFS=1`. Dagli indirizzi vengono tolti i parametri di
   tracciamento (`utm_*`, `fbclid`, `gclid`, ...) e i controlli di
   ordinamento/filtro dei negozi (`orderby`, `per_page`, `stock_status`,
   `min_price`, `max_price`, `filter_*`, `add-to-cart`), così la stessa pagina
   non viene letta più volte.
3. Rimuove le righe ripetute su molte pagine (menu, footer, avvisi cookie)
   secondo `BOILERPLATE_STRIP`, `BOILERPLATE_MIN_PAGES` (4) e
   `BOILERPLATE_PAGE_FRACTION` (0.3).
4. Con `--replace`, a questo punto ricrea la collezione.
5. Divide il testo in blocchi di `CHUNK_SIZE` caratteri (800) sovrapposti di
   `CHUNK_OVERLAP` (160), calcola gli embedding e li salva. Ogni blocco ha un
   identificativo derivato dall'indirizzo della pagina e dalla sua posizione:
   per questo una rilettura non crea duplicati.

Esempi:

```bash
# prima lettura di un sito, al massimo 500 pagine
chathelper ingest https://www.vostrosito.it --collection vostrosito --max-pages 500

# aggiornamento completo "da zero" dopo grandi cambiamenti al sito
chathelper ingest https://www.vostrosito.it --collection vostrosito --max-pages 500 --replace

# sito costruito interamente in JavaScript
chathelper ingest https://app.vostrosito.it --collection vostrosito --render
```

### 13.2 `chathelper serve` — avviare l'API per prove locali

Sintassi: `chathelper serve [opzioni]`

| Opzione | Cosa fa | Se omessa |
|---|---|---|
| `--collection NOME` | Collezione usata quando il widget non invia alcun `client_id`. Le richieste con `client_id` usano comunque la collezione indicata dal widget. | `QDRANT_COLLECTION` del `.env`. |
| `--site-name "Nome"` | Nome del sito per le risposte della collezione predefinita. | `SITE_NAME` del `.env`. |
| `--host INDIRIZZO` | Interfaccia di rete su cui ascoltare. `127.0.0.1` = solo questo computer; `0.0.0.0` = tutte le interfacce (da usare solo dietro un firewall o un proxy). | `127.0.0.1` |
| `--port NUMERO` | Porta TCP su cui ascoltare. | `8000` |
| `--ssl-certfile FILE` | Certificato (catena PEM) per servire direttamente in HTTPS. Non serve quando davanti c'è Apache, Caddy o nginx che fa già HTTPS. Equivalente alla variabile `SSL_CERTFILE`. | HTTP semplice |
| `--ssl-keyfile FILE` | Chiave privata PEM abbinata al certificato. Equivalente a `SSL_KEYFILE`. | — |

**In produzione `serve` non si usa.** Sul server il servizio `chathelper`
(systemd) avvia direttamente il server web Uvicorn con questa riga, i cui
parametri significano:

```
uvicorn chathelper.main:app --host 127.0.0.1 --port 8000 --workers 2 --proxy-headers --forwarded-allow-ips=127.0.0.1
```

| Parametro | Significato |
|---|---|
| `chathelper.main:app` | L'applicazione da servire (modulo `chathelper.main`, oggetto `app`). |
| `--host 127.0.0.1` | Ascolta solo in locale: dall'esterno si passa sempre da Apache in HTTPS. |
| `--port 8000` | Porta interna a cui Apache inoltra le richieste. |
| `--workers 2` | Due processi in parallelo per servire più visitatori contemporaneamente. |
| `--proxy-headers` | Legge gli header `X-Forwarded-*` inviati da Apache, così l'app conosce l'indirizzo IP reale del visitatore (usato dai limiti di richieste al minuto). |
| `--forwarded-allow-ips=127.0.0.1` | Fida di quegli header solo quando arrivano da Apache sulla stessa macchina. |

### 13.3 `chathelper init` — creare un file `.env` di partenza

Sintassi: `chathelper init` (nessuna opzione). Scrive un file `.env` con i
valori predefiniti nella cartella corrente. Se il file esiste già non lo
tocca e lo segnala. Serve solo per una prima installazione su un nuovo
computer.

### 13.4 `chathelper prune` — cancellare le conversazioni vecchie

Sintassi: `chathelper prune --days N`

| Opzione | Cosa fa |
|---|---|
| `--days N` (obbligatoria) | Cancella le conversazioni iniziate più di `N` giorni fa, insieme ai loro messaggi. `N` deve essere almeno 1. Stampa quante conversazioni ha eliminato. |

Richiede l'accesso a PostgreSQL configurato nel `.env`. Sul server viene
eseguito automaticamente ogni notte alle 04:15 con `--days 90`
(`/etc/cron.d/chathelper`): cambiare quel numero per modificare il periodo
di conservazione.

### 13.5 Backup della base di conoscenza

Sintassi: `python -m chathelper.backup_qdrant CARTELLA`

| Argomento | Cosa fa |
|---|---|
| `CARTELLA` (obbligatoria) | Cartella di destinazione, creata se non esiste. Per ogni collezione crea un'istantanea (snapshot) in Qdrant, la scarica qui, poi elimina la copia temporanea sul server Qdrant. Scrive anche `manifest.json` con l'elenco dei file, le dimensioni e la data. |

Richiede `QDRANT_URL` nel `.env` (non funziona in modalità "cartella
locale"). Sul server lo esegue lo script `scripts/backup-native.sh`, che
salva anche un dump di PostgreSQL e le somme di controllo in
`/srv/chathelper/backups/<data-ora>/` e conserva gli ultimi 14 backup
(variabile `KEEP`); gira ogni notte alle 03:15.

### 13.6 Script per chi amministra il server

| Comando | Cosa fa |
|---|---|
| `bash scripts/install-native.sh` | Installa o riallinea tutto il necessario sul server (Python, PostgreSQL, Qdrant, l'applicazione, i servizi systemd) tranne Apache. Si può rilanciare senza danni. Variabili opzionali: `CH_BASE` (cartella base, `/srv/chathelper`), `CH_REPO` (indirizzo Git), `QDRANT_VERSION`. |
| `bash scripts/backup-native.sh` | Backup completo (vedi 13.5). `KEEP=N` cambia quanti backup conservare. |
| `systemctl status chathelper` / `systemctl restart chathelper` | Stato / riavvio dell'assistente. Il riavvio è necessario dopo ogni modifica al file `.env`. |
| `journalctl -u chathelper -n 100 -f` | Ultime 100 righe di log dell'assistente, in aggiornamento continuo (`Ctrl+C` per uscire). |
| `curl -fsS https://srv.tallweb.eu/ready` | Verifica dall'esterno che database, Qdrant e i servizi del modello rispondano. |
| `cd /srv/chathelper/app && git pull --ff-only && /srv/chathelper/venv/bin/pip install -q -e . && systemctl restart chathelper` | Aggiorna l'applicazione all'ultima versione pubblicata. |
| `bash scripts/deploy.sh <azione>` | Solo per l'installazione alternativa con Docker Compose (non usata su `srv.tallweb.eu`). Azioni: `prepare`, `validate`, `up`, `update`, `backup`, `restart`, `status`, `logs [servizio]`, `ingest URL [opzioni di ingest]`, `prune --days N`, `down`. |

### 13.7 Impostazioni del file `.env` che influenzano i comandi

L'elenco completo, con commenti, è in `.env.example`. Le più rilevanti per i
comandi di questa sezione:

| Variabile | Significato | Predefinito |
|---|---|---|
| `QDRANT_COLLECTION` | Collezione usata quando `--collection` / `client_id` mancano. | `default` |
| `CRAWL_MAX_PAGES`, `CRAWL_SAME_DOMAIN`, `CRAWL_RENDER`, `CRAWL_PDFS`, `CRAWL_PDF_MAX_MB`, `CRAWL_MAX_PAGE_MB` | Limiti e modalità della lettura (le opzioni di `ingest` le sovrascrivono per una singola esecuzione). | 50 / 1 / 0 / 1 / 20 / 5 |
| `SITE_NAME`, `SITE_NAMES`, `SITE_STYLES` | Nome del sito nelle risposte; nomi e tono per collezione (`collezione=valore`, separati da `,` per i nomi e da `|` per i toni). | `this website` / vuoto / vuoto |
| `ALLOWED_ORIGINS` | Siti (con `https://`) autorizzati a usare il widget: ogni nuovo sito va aggiunto qui, seguito da un riavvio. | vuoto = tutti (solo per prove) |
| `TOP_K` | Quanti blocchi di testo vengono recuperati per ogni domanda. | 3 (sul server 6) |
| `LLM_MODEL`, `EMBED_MODEL`, `EMBED_DIM` | Modello di chat, modello di embedding e sua dimensione. Cambiare il modello di embedding richiede di rileggere tutti i siti con `--replace`. | — |
| `QA_TOKEN` / `QA_TOKEN_FILE` | Codice di accesso alla pagina delle conversazioni; vuoto = pagina disattivata. | vuoto |
