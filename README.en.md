# Tech News Radar

![Tech News Radar](docs/assets/banner.png)

[![Italiano](https://img.shields.io/badge/Lingua-Italiano-475569)](README.md)
[![English](https://img.shields.io/badge/Language-English-2563eb)](README.en.md)

A personal reader that brings technology, artificial intelligence, software
development, and economics news into one place.

Tech News Radar imports RSS/Atom feeds, lets readers search and filter articles,
manages sources and categories, and keeps per-user preferences and read states.
It includes a shared AI digest of the previous 24 hours, with links to the
sources. Gemini generation is active in the published instance; new
installations keep it disabled until explicitly configured.

In **My sources**, readers and administrators can follow the entire catalog or
remove all their subscriptions while preserving read states.

The responsive interface is available in Italian and English. The backend uses
Supabase PostgreSQL exclusively, with verified TLS and the private `tnr`
application schema.

Administrators have a Gemini statistics panel with tokens per attempt, daily and
monthly summaries, estimated costs, and reserved budget. Unavailable consumption is
explicitly marked.

## Local quickstart

Requirements: Python 3.13, Node.js 24, npm, and access to the Supabase project.

```sh
git clone https://github.com/giorgioinfo13/tech-news-radar.git
cd tech-news-radar
cp .env.example .env
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install --require-hashes -r backend/requirements-dev.txt
npm ci --prefix frontend
```

Complete `.env` with the Supabase endpoints, publishable key, and PostgreSQL URL
for the application role. Production migrations run only through the authorized
release workflow.

Then start the backend from the repository root:

```sh
cd backend
.venv/bin/python -m uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

Start the frontend in a second terminal:

```sh
npm run dev --prefix frontend
```

Open <http://127.0.0.1:5173>. Data is read from the configured Supabase database.

## Forks and deployment

The quickstart also works from a fork. Never commit the `.env` file. Collection
and release workflows are tied to the upstream repository; in a fork, adapt
their guards and configure your own variables, secrets, and services. See the
[deployment guide](docs/deployment.md) for a public installation.

Documentation: [development and tests](docs/development.md) ·
[architecture](docs/architecture.md) ·
[AI digest](docs/ai-briefs.md)

Distributed under the [MIT License](LICENSE). Third-party resources retain their
respective licenses.
