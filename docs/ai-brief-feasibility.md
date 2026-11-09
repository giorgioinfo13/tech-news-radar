# Sintesi / Radar Brief — analisi di fattibilità

Verifica documentale: **9 novembre 2026**. Questa è una proposta, non una funzione implementata.
L'utente ha comunicato di aver creato un account OpenRouter il 9 novembre 2026.
Durante questo lavoro non sono stati creati account, collegate chiavi, attivati o acquistati crediti,
effettuate richieste di inferenza o inviati dati del progetto a un modello.
La sola interrogazione OpenRouter è stata la lettura anonima del catalogo pubblico dei modelli.

## Raccomandazione

Un MVP compatibile con il vincolo gratuito è una **sintesi condivisa per categoria**, generata
su richiesta esplicita, al massimo una volta al giorno per categoria, salvata in PostgreSQL e
consultabile da tutti gli utenti approvati. Non è un riepilogo delle fonti personali.
Proporrei una sola chiave OpenRouter del progetto, un account senza saldo acquistato e un modello
esplicitamente gratuito. Il collegamento dell'account e l'attivazione richiedono un futuro incarico.

Il catalogo locale effettivamente letto in sola lettura contiene **8 categorie**: AI e LLM,
agenti AI, sviluppo software, modelli aperti, aziende tecnologiche, ricerca, economia e finanza,
notizie tecnologiche internazionali. Un controllo Supabase in sola lettura del 9 novembre 2026
ha confermato anche **8 categorie remote**, senza confrontarne nomi e contenuti.
Le formule sotto usano `C = 8`; riconfermare il numero al momento dell'implementazione.

Con otto categorie il volume nominale è otto chiamate al giorno indipendentemente da 3–5 utenti.
Impostare un tetto conservativo di **16 tentativi e 64.000 token riservati al giorno per tutto
il progetto**, ridotto ulteriormente quando la disponibilità del fornitore è inferiore.
Una sola generazione contemporanea, cooldown globale di 60 secondi e per categoria di un'ora
in caso di errore; massimo due tentativi per categoria e giorno, soltanto espliciti.
Niente ripiego automatico su modelli o servizi a pagamento, ricariche, acquisti o upgrade.

È sostenibile come servizio opzionale a bassa frequenza, con giorni senza generazione in caso
di indisponibilità. Non è possibile garantire disponibilità continua o gratuità permanente.
Se le quote reali scendono, ridurre a 2–4 categorie o a una sintesi ogni 48 ore prima di attivare
la funzione. Il lettore di notizie deve continuare a funzionare senza AI.

## Condiviso e personale

| Scelta | Consumo | Privacy e significato |
| --- | --- | --- |
| Condiviso per categoria | Una chiamata per categoria e finestra; riuso tra tutti | Riassume il catalogo condiviso. Nessuna sottoscrizione o lettura personale entra nel prompt |
| Personale per categoria | Fino a utenti × categorie × finestre | I testi selezionati possono rivelare indirettamente gli interessi, anche senza un nome nel prompt. Risultati e cache richiedono isolamento per utente |
| Condiviso, mostrato solo nelle categorie seguite | Uguale al condiviso | La visibilità può essere personalizzata, ma il testo resta una sintesi del catalogo, non delle fonti seguite |

La prima opzione è la raccomandazione. La terza è un'eventuale scelta di presentazione da
approvare separatamente. La seconda non rientra nell'MVP raccomandato.
Una cache condivisa non deve mai riutilizzare risultati personali per un altro utente.

## Contenuto e qualità

- Finestra mobile di 24 ore, fissata all'inizio della generazione e memorizzata in UTC.
  Mostrare intervallo, data/ora di generazione, categoria e indicazione «Da titoli e descrizioni RSS».
- Al massimo 12 notizie da fonti abilitate del catalogo condiviso, usando titolo e descrizione
  già salvati. Nessun download dell'articolo completo, scraping o ricerca del modello.
- Ordinare per pubblicazione, con acquisizione come ripiego dichiarato se la data manca.
  Escludere date future implausibili. Limitare il dominio più prolifico, ad esempio a tre notizie,
  per non trasformare una categoria in una sola fonte.
- Deduplicare URL normalizzati e titoli normalizzati con regole locali; accorpare titoli quasi
  identici senza introdurre embeddings. Non presentare il raggruppamento euristico come certezza.
- Usare un budget di input di 3.500 token inclusi istruzioni, nomi delle fonti e riferimenti.
  Troncare le descrizioni prima della richiesta. Il limite di 12 è un massimo, non un obiettivo
  da raggiungere ignorando il budget. Verificare il tokenizer del modello; in sua assenza usare
  un limite conservativo sui byte UTF-8 e ridurre l'input. Non stimare i token solo dal numero di parole.
- Output in italiano, 120–180 parole, massimo 500 token totali di completamento, inclusa eventuale
  elaborazione interna se il modello la conteggia. Preferire un modello non reasoning oppure
  con elaborazione disattivabile e limite documentato. Con 500 token alcuni modelli reasoning
  potrebbero non produrre testo utile: escluderli, senza aumenti automatici del budget.
- Se non ci sono articoli: stato «Nessuna notizia nel periodo», nessuna chiamata.
  Se tutte le descrizioni sono insufficienti: mostrare una selezione di titoli e link, senza
  chiamarla sintesi AI. Con dati misti, dichiarare gli elementi basati sul solo titolo.
- Richiedere un oggetto strutturato con testo e soli ID delle notizie fornite. Validare schema,
  lunghezza, ID e numero dei riferimenti. Risolvere i link dal database, non dall'output del modello.
  Le citazioni devono rimandare a elementi effettivamente inclusi nell'input.
- Non garantire l'assenza di errori fattuali con la sola validazione JSON. Mostrare l'origine RSS
  e i link verificabili; non inventare dettagli mancanti o affermare di avere letto gli articoli.

## Fornitori e collegamenti: stato verificato

### OpenRouter, chiave del progetto

La documentazione corrente indica **20 richieste/minuto e 50/giorno** per varianti `:free`
senza gli acquisti che danno accesso al livello superiore. La quota è condivisa nell'account:
creare altre chiavi non moltiplica la disponibilità. Il catalogo può cambiare e i singoli
provider possono limitare ulteriormente l'accesso. `GET /api/v1/key` espone ora il contatore
`free_model_daily_requests` con `used`, `limit`, `remaining`, riferiti al giorno UTC.
La soglia acquistata da 1.000 richieste/giorno è esclusa dal nostro progetto.
Fonti: [prezzi](https://openrouter.ai/pricing), [limiti e contatori](https://openrouter.ai/docs/api_reference/limits).

Il [catalogo pubblico](https://openrouter.ai/api/v1/models), letto senza autenticazione, riportava
12 varianti `:free` con prezzo input/output zero. Tra i candidati da valutare in un futuro test
approvato: `google/gemma-4-26b-a4b-it:free`, `google/gemma-4-31b-it:free` e
`liquid/lfm-3-1.7b:free`. Non è stata verificata la loro qualità in italiano, latenza, quota
assegnata all'account dell'utente o disponibilità compatibile con la privacy desiderata.
Non fissare un modello a pagamento come alternativa silenziosa.

La configurazione futura deve usare una allowlist di ID gratuiti verificati, prezzi zero per
ogni componente applicabile, `provider.max_price` pari a zero per input, output e richiesta,
e nessuna lista di fallback a pagamento. Non usare alias generici `auto`.
Preferire un ID fisso a un router casuale di modelli gratuiti, per controllare qualità e
politiche del provider. Un modello rimosso, un prezzo sconosciuto o nessun endpoint conforme
mantengono la generazione disabilitata. [Controlli di routing e prezzo](https://openrouter.ai/docs/guides/routing/provider-selection).

### OpenRouter personale tramite OAuth/PKCE

Il flusso ufficiale scambia un codice per una **API key controllata dall'utente**, non per
crediti gratuiti aggiuntivi. Usare PKCE S256, `state` monouso legato alla sessione Supabase,
callback HTTPS esatta e scadenza breve. L'utente può revocare la chiave sul provider.
Questo introduce un account OpenRouter per ciascun lettore e gestione di segreti personali.
Non offre il vantaggio di una sola quota condivisa e rende più difficile prevedere la disponibilità.
Fonte: [OAuth PKCE](https://openrouter.ai/docs/guides/overview/auth/oauth).

Per il requisito attuale non lo sceglierei. Non distribuire richieste tra gli account personali
per aggirare un blocco del progetto. Se venisse autorizzato in futuro, mantenere comunque un
contatore globale che blocchi tutti, oltre alle quote individuali, e separare le cache personali.

### Gemini API personale

Gemini Developer API offre un livello gratuito per alcuni modelli; il listino consultato include
Gemini 3.8 Flash, ma non tutti i modelli sono gratuiti. Le quote sono per progetto e modello,
non per chiave. I limiti effettivi vanno letti in AI Studio: non attribuire al futuro account
una quota universale presa da un esempio. Il ripristino RPD è a mezzanotte del Pacifico,
quindi non coincide con il giorno UTC di OpenRouter e cambia rispetto a Roma con l'ora legale.
Fonti: [prezzi Gemini](https://ai.google.dev/gemini-api/docs/pricing),
[limiti Gemini](https://ai.google.dev/gemini-api/docs/rate-limits).

È un'alternativa da valutare separatamente mantenendo il progetto nel livello gratuito,
senza collegare fatturazione o attivare servizi a pagamento. Un piano dell'app Gemini non è
una garanzia di credito Developer API. Chiavi personali non sono necessarie per l'MVP condiviso.

### OpenAI API personale e crediti inclusi

Le API rimangono un prodotto distinto dal piano chat, ma la documentazione corrente prevede
crediti API per abbonamenti **Pro e Business idonei**, dopo collegamento esplicito a un'organizzazione
API posseduta dallo stesso titolare. Pro: 100/200/500 USD al mese secondo il livello; Business:
20 USD per posto Standard o 100 USD Premium, con tetto condiviso di 500 USD/mese.
Sono richiesti almeno sette giorni di abbonamento pagato, titolarità e stessa email.
I crediti scadono al termine del ciclo e non si accumulano. Plus, Go e Free non sono idonei.
Nessun beneficio è stato attivato o verificato sull'account dell'utente.
Fonte: [crediti API per abbonati ChatGPT](https://developers.openai.com/api/docs/guides/chatgpt-api-credits).

Questi crediti coprono l'uso di API a tariffa: non rendono i modelli gratuiti in modo permanente.
In presenza di credito acquistato il consumo può proseguire dopo quello incluso.
Il vincolo richiesto è più stretto: **solo modelli gratuiti**, quindi questa non è una soluzione
ammessa per l'MVP, anche se l'utente fosse già titolare di un piano idoneo.
Non attivare ricariche o acquisti e non usare questa possibilità come fallback.

### Sign in with ChatGPT e utilizzo del piano

L'offerta esiste: login e autorizzazione all'uso del piano sono capacità distinte.
Il solo login non consente inferenza. Il flusso documentato richiede consenso e scope concessi
per usare il piano; non dà accesso alle conversazioni dell'utente.
Il cookbook riguarda progetti open source e personali eseguiti localmente. Per app pagate
**o ospitate da remoto** richiede di ottenere accesso prima di offrirle agli utenti.
Tech News Radar su Vercel/Render ricade nel caso remoto, anche con repository MIT e pochi amici.
Non è quindi un'integrazione immediatamente disponibile o autorizzata per questa distribuzione.
Fonti: [cookbook](https://developers.openai.com/cookbook/articles/sign-in-with-chatgpt?site_locale=en),
[quickstart e disponibilità](https://developers.openai.com/siwc/quickstart).

Non riutilizzare token Codex, cookie di sessione, file delle credenziali locali o proxy non
supportati. Il collegamento AI non deve sostituire Google/Supabase né autorizzare lettori
senza invito o con accesso revocato. Anche un eventuale accesso approvato consumerebbe un piano
personale con proprie quote, non una quota gratuita OpenRouter condivisa.

### Anthropic API personale

Il listino Claude API applica prezzi per token. Sono ora documentati anche crediti inclusi
per piani Max (100 USD), Ultra (200 USD) e Team (fino a 500 USD condivisi per mese), con
attivazione, requisiti di idoneità e scadenza. Non presumere che qualsiasi piano Claude dia
credito API o che quello disponibile possa sostenere il progetto gratuitamente.
Fonti: [prezzi](https://platform.claude.com/docs/en/about-claude/pricing),
[crediti per abbonati](https://platform.claude.com/docs/en/about-claude/api-credits-for-subscribers).
Come OpenAI API, usa modelli tariffati: escluso dall'MVP che richiede esclusivamente modelli gratuiti.

## Quota globale, richieste concorrenti e ripristino

Questo è un requisito per la futura implementazione, non codice già presente.
Il frontend non è il punto di controllo della quota.

1. Autenticare ogni POST con Supabase e verificare utente attivo. Le GET leggono soltanto risultati salvati.
2. Validare categoria, finestra, disponibilità di un modello gratuito, freschezza della cache e input sufficiente.
3. Aprire una breve transazione PostgreSQL: bloccare la riga della quota giornaliera condivisa,
   verificare il blocco fornitore e riservare **un tentativo più 4.000 token** prima della rete.
   Il limite è `min(16, quota gratuita disponibile verificata)`, senza superare il budget token.
4. Creare nella stessa transazione una richiesta con chiave univoca per categoria/finestra/versione
   e una lease globale persistente. Una richiesta duplicata riceve lo stato esistente, non un secondo invio.
5. Completare la transazione, chiamare un solo endpoint gratuito con timeout complessivo limitato,
   validare e salvare il risultato. Nessuna transazione o connessione DB resta occupata durante l'inferenza.
6. Conteggiare anche tentativi falliti, timeout, output rifiutati e interruzioni come consumati.
   Non rimborsare automaticamente una prenotazione quando non è certo se il provider ha ricevuto la richiesta.
   Il conteggio locale conservativo può esaurirsi prima del limite del provider: è intenzionale.
7. Quando budget o quota giornaliera sono esauriti, tutti i POST, incluse chiamate dirette e chiavi
   di idempotenza nuove, restituiscono `429` con un codice applicativo stabile e il testo:
   **«Limite gratuito giornaliero raggiunto. La generazione sarà nuovamente disponibile al ripristino della quota»**.
   Le richieste simultanee devono poter consumare soltanto l'ultimo slot effettivamente disponibile.
8. Registrare blocco e scadenza in PostgreSQL, non in memoria. Su quota provider esaurita aprire
   il blocco globale; nessuna catena di retry automatici o cambio di account/modello per aggirarlo.
9. OpenRouter definisce il contatore gratuito sul **giorno UTC**: nuova giornata alle 00:00 UTC,
   alle 01:00 a Roma in inverno e alle 02:00 in estate. Usare l'orologio del database e il contatore
   ufficiale, non il fuso del browser. Dopo il cambio giornata, una sola richiesta coordinata
   verifica quota e disponibilità prima di riaprire. Se la verifica fallisce, restare chiusi.
10. Distinguere quota giornaliera, limite al minuto e indisponibilità del provider. Per un limite
    breve usare `Retry-After`/metadati documentati; per una risposta ambigua mantenere il blocco
    conservativo e richiedere una verifica, senza martellare il provider.

I contatori ufficiali servono a riconciliare altri consumi dell'account, non sostituiscono la
prenotazione atomica locale. Raccomandato account/chiave dedicati al progetto, senza altri client.
Una chiave nuova, una nuova sessione o un riavvio Render non azzerano le quote.
Il limite locale di token è una protezione applicativa: non è una quota token gratuita garantita da OpenRouter.
Le proprietà del contatore e i reset derivano dalla [documentazione ufficiale dei limiti](https://openrouter.ai/docs/api_reference/limits).

## Render Free: richiesta esplicita o schedulazione

Render Free sospende dopo 15 minuti senza traffico; il risveglio richiede circa un minuto.
Offre 750 ore d'istanza al mese per workspace e filesystem effimero.
Fonti: [Render Free](https://render.com/docs/free).
Nessun modello locale: CPU e memoria rimangono dedicate al backend.

**Su richiesta, scelta MVP:** il caricamento del lettore e della cache risveglia prima il backend.
Il pulsante di generazione diventa disponibile dopo una risposta del servizio. Il POST esegue
una sola inferenza con deadline proposta di 20–25 secondi. Questo riduce il rischio di sommare
cold start e inferenza oltre i 90 secondi del client o il limite del proxy.
Se non è possibile mantenere questo tempo con modelli gratuiti, ridurre input/ambito o lasciare
la funzione indisponibile; non introdurre un servizio pagato.

**Schedulazione esterna:** una futura GitHub Action a bassa frequenza potrebbe chiamare Render
con un segreto macchina dedicato, separato da quello di raccolta. Deve usare le stesse quote,
lease e chiavi idempotenti nel database. Vantaggi: richiesta diretta a Render e cache pronta.
Svantaggi: esecuzione ritardata o saltata, timeout, consumo dei minuti e disponibilità del piano
GitHub. Il timer non è una garanzia di puntualità; non è implementato o attivato qui.
La disponibilità gratuita dipende anche da tipo e visibilità del repository, da riconfermare.

Non usare timer interni come sola garanzia né `BackgroundTasks`/liste in memoria come coda affidabile.
Persistenza minima proposta: record richiesta con stato, lease, scadenza, fingerprint, tentativo e consumo.
Un arresto lascia una richiesta incerta: al ritorno, dopo scadenza, segnarla interrotta senza
reinviarla automaticamente e senza recuperare lo slot. Non si può garantire «exactly once»
verso un provider senza idempotenza da esso documentata. Risultati validi si salvano solo se la
lease appartiene ancora al tentativo originale; non lanciare un sostituto mentre il vecchio può essere attivo.
La notizia resta leggibile durante questi problemi. Niente keep-alive frequente per impedire la sospensione.

## Sicurezza e dati

**Segreti del progetto:** chiave solo in configurazione backend, mai `VITE_*`, Git, URL, log,
analytics o risposte di consultazione. API di stato restituisce soltanto disponibilità e reset,
non chiavi o dettagli grezzi del provider. Nessuna richiesta AI dall'app frontend.

**Eventuali chiavi personali, fuori MVP:** uso temporaneo nel POST evita conservazione durevole,
ma espone la chiave alla memoria del browser e del backend e non sopravvive a un riavvio.
Non salvarla in localStorage o log. La conservazione cifrata consente uso successivo, ma richiede
cifratura autenticata, chiave principale separata dal database, versionamento e rotazione,
accesso per proprietario, revoca, cancellazione e gestione delle copie di sicurezza.
Nessun endpoint può rileggere il segreto; mostrare soltanto metadati mascherati.
La revoca dell'accesso all'app blocca anche l'uso della connessione AI, non solo la UI.
Preferire la singola chiave di progetto evita tutto questo carico nel primo rilascio.

**Prompt injection:** RSS è input non attendibile. Separare istruzioni e dati in uno schema,
non inserire testo dei feed nel messaggio di sistema, vietare esecuzione di istruzioni contenute
nelle notizie. Il modello non riceve strumenti, rete, file, segreti o capacità di modificare dati.
Non bastano frasi come «ignora le istruzioni»: la protezione principale è l'assenza di capacità
pericolose e la validazione dell'output. Rendering come testo React, nessun HTML esterno.
L'app genera i link da ID verificati e URL HTTP/HTTPS già controllati.

Inviare solo titoli, estratti RSS limitati, fonte, date e riferimenti opachi alle notizie.
Non inviare identità Google, email, token, ID del lettore, letture o sottoscrizioni personali.
Valutare diritti e condizioni delle fonti prima di un invio a terzi; non ricopiare articoli completi.

**Retention e training:** OpenRouter e il provider finale sono due soggetti distinti.
OpenRouter descrive eccezioni di conservazione per sicurezza e possibilità di opt-in ai log;
i provider hanno proprie politiche. Escludere routing verso provider che addestrano sui prompt,
valutare retention e localizzazione e non attivare logging dei contenuti. Se nessun endpoint
gratuito rispetta i requisiti, generazione disabilitata.
Fonti: [raccolta dati OpenRouter](https://openrouter.ai/docs/guides/privacy/data-collection),
[politiche dei provider](https://openrouter.ai/docs/guides/privacy/provider-logging).

Gemini gratuito può usare contenuti per miglioramento e revisione umana secondo i termini generali.
Per SEE, Svizzera e Regno Unito i termini applicano però le disposizioni sul trattamento dei
servizi a pagamento anche alla quota gratuita: non uso per miglioramento, con retention limitata
per sicurezza. Verificare l'applicabilità al titolare italiano e alla configurazione effettiva,
senza promettere assenza totale di conservazione. [Termini Gemini](https://ai.google.dev/gemini-api/terms).

OpenAI API non usa normalmente i contenuti per training senza opt-in; i log di abuso possono
rimanere fino a 30 giorni, con eccezioni, e lo stato applicativo dipende dall'endpoint/configurazione.
[Controlli dati OpenAI](https://developers.openai.com/api/docs/guides/your-data).
Per Anthropic API la conservazione ordinaria di input/output è fino a 30 giorni salvo eccezioni
contrattuali, sicurezza o obblighi legali; verificare anche condizioni del modello selezionato.
[Retention Anthropic](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data).
Anthropic dichiara inoltre che i dati dei prodotti commerciali/API non sono usati per training
per impostazione predefinita; feedback o consenso possono cambiare questo trattamento.
[Uso per training Anthropic](https://privacy.claude.com/en/articles/7996868-is-my-data-used-for-model-training).
Non trasferire automaticamente le condizioni API ai flussi di utilizzo dei piani chat.

Un futuro rilascio AI richiede una propria informativa aggiornata prima dell'attivazione.
La privacy modificata in questo lavoro descrive soltanto le proposte di fonti.

## Stime per 3–5 utenti e otto categorie

Ipotesi di progetto, non misure: 3.500 token input + 500 output al massimo per chiamata;
16 KB inviati e 3 KB ricevuti per chiamata, arrotondati; risultato e riferimenti occupano 8 KB
prima dell'overhead PostgreSQL. Non includono TLS, log, retry, indici, vacuum e dati degli articoli.
Una stima reale deve misurare byte/token con il modello scelto e `pg_total_relation_size`.

| Scenario giornaliero | Chiamate | Input + output massimi | Traffico AI/giorno | Traffico AI/30 giorni |
| --- | ---: | ---: | ---: | ---: |
| 8 categorie condivise, 3 o 5 utenti | 8 | 28.000 + 4.000 | 152 KB | 4,56 MB |
| Tetto condiviso, inclusi errori | 16 | 56.000 + 8.000 | 304 KB | 9,12 MB |
| Personale, 3 utenti × 8 categorie | 24 | 84.000 + 12.000 | 456 KB | 13,68 MB |
| Personale, 5 utenti × 8 categorie | 40 | 140.000 + 20.000 | 760 KB | 22,8 MB |
| Personale 5 utenti, due aggiornamenti | 80 | 280.000 + 40.000 | 1,52 MB | 45,6 MB |

I casi personali da 24/40 chiamate superano il nostro tetto prudenziale e lasciano meno margine
rispetto alle 50 richieste gratuite dell'account. Il caso da 80 non è sostenibile senza riduzione.
Non aumentare il budget comprando crediti. Nel condiviso, 3–5 utenti non moltiplicano l'inferenza.

Conservare **7 giorni**, al massimo una sintesi riuscita per categoria/giorno: 56 risultati,
circa 448 KB logici; stimare 1–2 MB con metadati e indici come riserva da misurare.
Con cache personale diventano 168–280 risultati, circa 1,34–2,24 MB logici.
Conservare richieste/quote dettagliate solo quanto serve alla finestra di sicurezza, proposta 7 giorni;
non conservare prompt completi. Pulizia a piccoli lotti prima di nuove generazioni e attraverso
un eventuale trigger esterno autorizzato; limite rigido di righe anche se la pulizia temporale ritarda.

Ipotizzando quattro visite giornaliere e la lettura di tutte le otto sintesi da 8 KB:
3 utenti producono circa 2880 letture e 23 MB/mese; 5 utenti 4800 letture e 38,4 MB/mese.
Questo traffico attraversa database/backend/proxy, secondo dove viene letta la cache; **zero nuove
chiamate AI**. È distinto dal traffico degli articoli, asset, autenticazione e feed.

| Servizio | Limiti pubblici pertinenti | Implicazione |
| --- | --- | --- |
| OpenRouter gratuito | 50 richieste/giorno, 20/minuto, oltre alle restrizioni dei provider | Budget locale 16 tentativi; spesa AI zero solo con endpoint realmente gratuiti |
| Supabase Free | 500 MB database, 5 GB egress, 50.000 utenti attivi/mese; pausa dopo inattività | Otto sintesi sono piccole, ma articoli, indici, history e letture crescono separatamente |
| Render Free / Hobby | 750 ore/mese condivise, sospensione per inattività; Hobby corrente 5 GB outbound | Contare anche traffico a Supabase, feed request, client e AI; non affidarsi al solo traffico dei prompt |
| Vercel Hobby | 100 GB Fast Data Transfer, 10 GB Fast Origin Transfer, 1 milione CDN requests; uso personale non commerciale | Il proxy API e gli asset consumano quote; al limite può sospendersi la funzione interessata |

Fonti: [Supabase](https://supabase.com/pricing), [Render Free](https://render.com/docs/free),
[Render outbound](https://render.com/docs/outbound-bandwidth), [Vercel Hobby](https://vercel.com/docs/plans/hobby).

Render può fatturare banda extra se esiste un metodo di pagamento; in sua assenza sospende
quando termina la quota. Prima di attivare AI, verificare il piano e le protezioni di spesa
correnti senza modificarli in questo incarico. Non basta il nome «Free» del compute per garantire
che qualsiasi risorsa dell'account sia incapace di generare addebiti.
Il vincolo è zero spesa: se la configurazione effettiva non lo garantisce, non attivare la generazione.

I circa 0,03 GB e 3,32 MB di `tnr.articles` segnalati dall'utente il 9 novembre sono misure storiche
indicative, non una verifica attuale né una stima della capacità. Gli indici sono separati dalla
misura della sola tabella. Non esiste una retention automatica dello storico articoli; anche
fonti non seguite vengono raccolte se abilitate. Questo può diventare il consumo dominante.
Misurare consumo complessivo e crescita settimanale prima del rilascio; una politica articoli
richiederebbe un incarico separato, senza cancellazioni implicite in questo MVP.

## Raccomandazioni personali e decisioni aperte

Filtri/raccomandazioni AI personali sono un'altra funzione: implicano profili di interesse,
possibile invio indiretto di preferenze, cache isolate e ulteriori chiamate. Non includerli nelle
sintesi. Per ora preferire i filtri e le sottoscrizioni deterministiche già presenti.

Prima di implementare l'AI occorre decidere e autorizzare:

1. Nome visibile e conferma della sintesi **condivisa**. L'utente richiede un pulsante con icona AI
   da definire; l'apertura dei risultati salvati non deve generare richieste al modello.
2. Collegamento futuro dell'account OpenRouter creato dall'utente, con chiave dedicata al backend,
   senza acquisti o ricariche. Quote e impostazioni dell'account non sono ancora state verificate.
3. Provider/modello gratuito compatibile con privacy e test qualitativi italiani su dati pubblici.
4. Generazione su richiesta esplicita (raccomandata) e quali utenti possono richiederla.
   Tutti rimangono soggetti allo stesso blocco globale; la prima richiesta valida alimenta la cache comune.
5. Budget 16 tentativi/64.000 token, una sintesi riuscita per categoria/giorno, retention sette giorni.
6. Verifica delle quote effettive e assenza di meccanismi di spesa nell'infrastruttura.
7. Test di esaurimento all'ultimo slot concorrente, errori, reset UTC, sospensione, riavvio,
   prompt injection, revoca, modello rimosso e GET che non generano.

Nessun codice, tabella, chiave, timer o endpoint AI è stato aggiunto in questo lavoro.
