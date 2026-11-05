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

Il progetto è in sviluppo. L'interfaccia responsive permette di consultare e cercare
notizie, filtrare per fonte e categoria e gestire lo stato letto/non letto.
Dalle pagine Fonti e Categorie puoi organizzare i feed RSS/Atom, avviare aggiornamenti
manuali e consultarne gli esiti. Il backend gestisce deduplicazione e persistenza SQLite.
Gli aggiornamenti automatici sono ancora da implementare. Non sono presenti fonti
preconfigurate: il primo passo è aggiungere un feed e aggiornarlo. L'interfaccia
è attualmente in italiano.

## Tecnologie

- **Interfaccia:** React, TypeScript, Vite e Tailwind CSS.
- **Backend:** Python e FastAPI.
- **Persistenza:** SQLite con SQLAlchemy e migrazioni Alembic.
- **Raccolta:** feedparser, httpx e defusedxml. APScheduler è previsto per gli aggiornamenti automatici.

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
Le dipendenze di terze parti mantengono le rispettive licenze.
