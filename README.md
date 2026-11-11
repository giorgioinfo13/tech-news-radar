# Tech News Radar

![Tech News Radar](docs/assets/banner.png)

[![Italiano](https://img.shields.io/badge/Lingua-Italiano-2563eb)](README.md)
[![English](https://img.shields.io/badge/Language-English-475569)](README.en.md)

Un lettore personale per raccogliere in un unico posto notizie su tecnologia,
intelligenza artificiale, sviluppo software ed economia.

Tech News Radar importa feed RSS/Atom, permette di cercare e filtrare gli
articoli, gestisce fonti e categorie e conserva preferenze e stato di lettura
per ogni utente. Include una rassegna AI condivisa delle ultime 24 ore, con
collegamenti alle fonti. La generazione tramite Gemini è attiva nell’istanza
pubblicata; nelle nuove installazioni resta disattivata finché non viene
configurata esplicitamente.

L’interfaccia responsive è disponibile in italiano e inglese. In locale usa
SQLite e non richiede account cloud; autenticazione multiutente e distribuzione
pubblica sono configurazioni separate.

## Quickstart locale

Requisiti: Python 3.13, Node.js 24 e npm.

```sh
git clone https://github.com/giorgioinfo13/tech-news-radar.git
cd tech-news-radar
cp .env.example .env
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install --require-hashes -r backend/requirements-dev.txt
npm ci --prefix frontend
cd backend
.venv/bin/alembic upgrade head
cd ..
```

Per accedere ai dati senza servizi cloud, abilita nell’`.env` locale:

```dotenv
TNR_LOCAL_USER_ID=00000000-0000-0000-0000-000000000001
VITE_LOCAL_MODE=true
```

Avvia quindi il backend dalla radice del repository:

```sh
cd backend
.venv/bin/python -m uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

In un secondo terminale avvia il frontend:

```sh
npm run dev --prefix frontend
```

Apri <http://127.0.0.1:5173>. Il database iniziale non contiene fonti: puoi
aggiungerle dall’interfaccia di amministrazione.

## Fork e distribuzione

Il quickstart funziona anche da una fork. Non committare mai il file `.env`.
I workflow di raccolta e rilascio sono legati al repository originario: in una
fork, adatta le guardie e configura variabili, segreti e servizi propri. Per una
distribuzione pubblica consulta la
[guida alla distribuzione](docs/deployment.md).

Documentazione: [sviluppo e test](docs/development.md) ·
[architettura](docs/architecture.md) ·
[rassegna AI](docs/ai-briefs.md)

Distribuito con [licenza MIT](LICENSE). Le risorse di terze parti mantengono le
rispettive licenze.
