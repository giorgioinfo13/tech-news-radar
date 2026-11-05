# Starter sources

Verification date: **2026-11-05**. Each included URL returned RSS/Atom with usable
articles through the application's guarded downloader and parser. Availability can change.
This catalog stores source metadata only. Article content retains the publisher's rights.

| Source | Verified feed | Initial category |
| --- | --- | --- |
| OpenAI | <https://openai.com/news/rss.xml> | Artificial intelligence |
| Google DeepMind | <https://deepmind.google/blog/rss.xml> | Artificial intelligence |
| Hugging Face | <https://huggingface.co/blog/feed.xml> | Open models |
| Mistral AI | <https://mistral.ai/news/rss> | Open models |
| Salvatore Sanfilippo (antirez) | <https://antirez.com/rss> | Software engineering |
| Simon Willison | <https://simonwillison.net/atom/everything/> | AI agents |
| Hacker News | <https://news.ycombinator.com/rss> | Software engineering |
| arXiv — Artificial Intelligence | <https://rss.arxiv.org/rss/cs.AI> | Research |
| MacRumors | <https://feeds.macrumors.com/MacRumors-All> | Technology companies |
| TechCrunch | <https://techcrunch.com/feed/> | Technology companies |
| Wired Italia | <https://www.wired.it/feed/rss> | International technology |

The arXiv feed covers `cs.AI`, not all arXiv subjects. Hacker News links to submitted
articles, which can come from other publishers. Category assignments are editable suggestions.
The antirez source covers his blog. GitHub and YouTube integrations remain future work.

## Sources not imported

- **Anthropic:** [News](https://www.anthropic.com/news) is accessible, but no working official RSS/Atom feed was verified.
  The checked `/news/rss.xml` and `/rss.xml` endpoints returned HTTP 404.
- **Reuters Technology:** [Technology](https://www.reuters.com/technology/) remains a requested source.
  The legacy `https://feeds.reuters.com/reuters/technologyNews` hostname did not resolve during the check.
  No working public replacement was verified. Thomson Reuters investor feeds cover a different subject.

These observations do not prove that no feed exists. A Feedly subscription can use a
different integration. An exported Feedly OPML file or exact feed URL can support a later check.
No third-party scraper, paid feed service, or unofficial replacement is included.

## Import and edit

Follow the [local setup instructions](development.md#use-the-interface).
The catalog is in [source_catalog.json](../backend/app/source_catalog.json).
Import is explicit and matches feed URLs. Existing settings remain unchanged.
Use **Fonti** to edit, disable, delete, or refresh imported sources.

To propose another default, verify its URL through the collector first.
Record the verification date and category, then update the catalog and this table.
Automated tests use local fixtures and mocked HTTP. They do not require these sites.
