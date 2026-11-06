# Tech News Radar

![Tech News Radar](docs/assets/banner.png)

[![Italiano](https://img.shields.io/badge/Lingua-Italiano-2563eb)](README.md)
[![English](https://img.shields.io/badge/Language-English-475569)](README.en.md)

Un posto per seguire le notizie che ti interessano, dalle fonti che scegli tu.

Tech News Radar è un progetto personale per raccogliere e consultare notizie su
tecnologia, intelligenza artificiale, sviluppo software ed economia.
L'obiettivo è un lettore semplice e personalizzabile, da eseguire sul proprio
computer, con fonti gestibili dall'interfaccia.

## Il progetto

La prima versione punta a offrire:

- Raccolta di articoli da feed RSS e Atom.
- Gestione delle fonti e organizzazione per categoria.
- Consultazione cronologica, ricerca e filtri.
- Stato letto/non letto e collegamento all'articolo originale.
- Aggiornamenti automatici e manuali, con errori visibili.

Il progetto privilegia semplicità, leggibilità del codice e poche dipendenze
operative. Le funzioni di base non richiederanno servizi a pagamento o modelli AI.

## Stato

Il progetto è in sviluppo. L'interfaccia editoriale responsive permette di consultare e cercare
notizie, filtrare per fonte e categoria e gestire lo stato letto/non letto.
Dalle pagine Fonti e Categorie puoi organizzare i feed RSS/Atom, avviare aggiornamenti
manuali e consultarne gli esiti. Il backend gestisce deduplicazione e persistenza SQLite o PostgreSQL.
SQLite resta la scelta predefinita per l'avvio locale senza account cloud.
Il [supporto PostgreSQL per Supabase](docs/postgresql.md) usa gli stessi modelli e servizi.
Il backend distingue amministratore e lettori, con sottoscrizioni e stato di lettura personali.
Login Google, inviti, onboarding e deploy pubblico non sono ancora disponibili.
Le prove locali usano un'identità configurata esplicitamente nel backend: vedi il [modello multiutente](docs/multiuser.md).
Il backend aggiorna automaticamente le fonti attive, di norma ogni 60 minuti, mentre è in esecuzione. Puoi aggiungere i feed
dall'interfaccia oppure importare il [catalogo iniziale di 11 fonti verificate](docs/sources.md).
L'interfaccia è attualmente in italiano.

## Prova locale

Dopo il [setup iniziale](docs/development.md#setup), le migrazioni e la [configurazione dell'identità locale](docs/development.md#run-the-backend), avvia backend e
frontend in due terminali, dalla cartella del progetto:

```sh
# Terminale 1
cd backend
.venv/bin/python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

```sh
# Terminale 2
cd frontend
npm run dev
```

In un terzo terminale importa le fonti; il backend raccoglierà i primi articoli automaticamente:

```sh
cd backend
.venv/bin/python -m app.catalog
```

Apri [Tech News Radar in locale](http://127.0.0.1:5173). Il catalogo include antirez,
OpenAI, DeepMind, Hugging Face, Mistral, Simon Willison, Hacker News, arXiv,
MacRumors, TechCrunch e Wired Italia. Tutte le fonti restano modificabili.
L'importazione ripetuta conserva le impostazioni delle fonti con lo stesso URL.
Per seguire le fonti appena importate usa `PUT /api/subscriptions/{source_id}` da `/docs`.
Le fonti già presenti prima della migrazione multiutente restano seguite dal proprietario.
La selezione delle sottoscrizioni nell'interfaccia arriverà con l'onboarding.
La prima raccolta inizia con una scansione successiva, normalmente entro 30 secondi se il collector è libero.
Puoi anche avviare un aggiornamento da **Fonti → Aggiorna**. Ricarica la pagina per vedere i nuovi articoli.
La [configurazione](docs/development.md#automatic-collection) permette di disattivare la raccolta automatica e cambiare gli intervalli.
Ferma i server con `Ctrl+C` nei rispettivi terminali.

## Tecnologie

- **Interfaccia:** React, TypeScript, Vite e Tailwind CSS.
- **Backend:** Python e FastAPI.
- **Persistenza:** SQLite o PostgreSQL (Psycopg 3), con SQLAlchemy e migrazioni Alembic.
- **Raccolta:** feedparser, httpx e defusedxml. Raccolta periodica con la libreria standard Python.

## Sviluppo

Le [istruzioni di sviluppo](docs/development.md) descrivono l'avvio locale e i
controlli disponibili. Le [note di architettura](docs/architecture.md) descrivono
il perimetro e i prossimi passi.

I contributi possono partire da una piccola modifica concordata tramite issue o
pull request. Le due versioni del README devono mantenere gli stessi contenuti.

## Licenza

Il progetto è distribuito con [licenza MIT](LICENSE).
Puoi usarlo, modificarlo e ridistribuirlo, anche per scopi commerciali,
conservando l'avviso di copyright e la licenza. Il software è fornito senza garanzie.
Le risorse di terze parti, incluse skill e font locali, mantengono le rispettive licenze.
