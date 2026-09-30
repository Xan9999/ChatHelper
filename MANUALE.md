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
}(document,"https://indirizzo-fornito","vostro-codice-sito","it");
</script>
```

Non serve capire il funzionamento interno — bastano due informazioni, che vi
verranno fornite già pronte:

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
