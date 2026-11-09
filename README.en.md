# Tech News Radar

![Tech News Radar](docs/assets/banner.png)

[![Italiano](https://img.shields.io/badge/Lingua-Italiano-475569)](README.md)
[![English](https://img.shields.io/badge/Language-English-2563eb)](README.en.md)

The news that interests you, gathered in one place.

Tech News Radar collects news about technology, artificial intelligence,
software development, and economics from selected sources. It lets you search
and filter articles, track what you have read, and open the original content.

The goal is a simple online space, initially designed for a small group of
friends with restricted access. An administrator curates the source catalog
and categories; each reader chooses which sources to follow and keeps their
own reading status.

**The project is in development.** The reader is published with Google sign-in
restricted to approved users and personal source selection. Local development
remains available; new features require a coordinated release.

Italian is the default interface language. In the top-right menu, select
**Lingua → English**. The browser keeps this preference after sign-out.
Articles and source names keep their original language.

With **Suggest a source**, readers suggest new sources and the administrator
approves or rejects them. See [how source proposals work](docs/architecture.md#source-proposals).

**AI digest** is an experimental feature, implemented locally and not yet active.
It provides one shared digest of the last 24 hours, updated at most hourly
when new material and Gemini 3.1 Flash-Lite are available.
It is prepared for Gemini through OpenRouter BYOK, with a paid API and a shared
local budget of USD 2.00 per month.
Activation remains blocked until token and cost verification is complete.
See [behavior and limits](docs/ai-briefs.md).

Documentation: [Architecture and features](docs/architecture.md) · [Development and tests](docs/development.md) · [Authentication and permissions](docs/authentication.md) · [Deployment and database](docs/deployment.md) · [AI digest and budget](docs/ai-briefs.md)

Distributed under the [MIT License](LICENSE). Third-party resources retain their respective licenses.
