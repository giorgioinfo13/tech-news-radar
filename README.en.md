# Tech News Radar

![Tech News Radar](docs/assets/banner.png)

[![Italiano](https://img.shields.io/badge/Lingua-Italiano-475569)](README.md)
[![English](https://img.shields.io/badge/Language-English-2563eb)](README.en.md)

A place to follow the news that matters to you, from sources you choose.

Tech News Radar is a personal project for news about technology, artificial
intelligence, software development, and economics.
The goal is a simple, customizable reader that runs on your computer, with
source management through a web interface.

## About the project

The first version aims to provide:

- Article collection from RSS and Atom feeds.
- Source management and categories.
- Chronological views, search, and filters.
- Read/unread status and links to original articles.
- Automatic and manual updates, with visible errors.

The project prioritizes simplicity, readable code, and few operational
dependencies. Core features will not require paid services or AI models.

## Status

The project is in development. The responsive interface supports article search,
source/category filters, and read/unread status.
The Sources and Categories pages let you organize RSS/Atom feeds, refresh them
manually, and inspect collection results. The backend handles deduplication and SQLite storage.
Automatic updates are not implemented yet. No sources are preconfigured: start
by adding a feed and refreshing it. The interface is currently in Italian.

## Technologies

- **Interface:** React, TypeScript, Vite, and Tailwind CSS.
- **Backend:** Python and FastAPI.
- **Persistence:** SQLite with SQLAlchemy and Alembic migrations.
- **Collection:** feedparser, httpx, and defusedxml. APScheduler is planned for automatic updates.

## Development

The [development guide](docs/development.md) describes local setup and available
checks. The [architecture notes](docs/architecture.md) describe the scope and
next steps.

Contributions can start with a small change agreed through an issue or pull
request. Keep both README versions equivalent when you change their content.

## License

The project is available under the [MIT License](LICENSE).
You can use, modify, and redistribute it, including for commercial purposes,
provided you retain the copyright and license notices. The software comes without warranties.
Third-party dependencies retain their respective licenses.
