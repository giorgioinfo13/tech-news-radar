# Tech News Radar

![Tech News Radar](docs/assets/banner.png)

[![Italiano](https://img.shields.io/badge/Lingua-Italiano-2563eb)](README.md)
[![English](https://img.shields.io/badge/Language-English-475569)](README.en.md)

Le notizie che ti interessano, raccolte in un unico posto.

Tech News Radar raccoglie notizie su tecnologia, intelligenza artificiale,
sviluppo software ed economia dalle fonti selezionate. Permette di cercare e
filtrare gli articoli, tenere traccia delle letture e aprire i contenuti originali.

L’obiettivo è uno spazio online semplice, pensato inizialmente per un piccolo
gruppo di amici con accesso riservato. Un amministratore cura il catalogo delle
fonti e le categorie; ogni lettore sceglie quali fonti seguire e mantiene il
proprio stato di lettura.

**Il progetto è in sviluppo.** Il lettore è pubblicato con accesso Google riservato
agli utenti approvati e scelta delle fonti personali. Rimane disponibile anche
lo sviluppo locale; le nuove funzioni richiedono un rilascio coordinato.

L’italiano è la lingua predefinita. Nel menu in alto a destra puoi scegliere
**Lingua → English**; la preferenza rimane nel browser anche dopo il logout.
Articoli e nomi delle fonti mantengono la lingua originale.

Con **Proponi una fonte** i lettori suggeriscono nuove fonti e l’amministratore
le approva o rifiuta. Consulta il [funzionamento delle proposte](docs/architecture.md#source-proposals).

**Rassegna AI** è una funzione sperimentale, sviluppata in locale e non ancora attiva.
Prevede una rassegna condivisa delle ultime 24 ore, aggiornata al massimo ogni ora
quando ci sono nuovi contenuti e Gemini 3.1 Flash-Lite è disponibile.
È predisposta per l’API Google Gemini diretta, a pagamento, con budget locale
prudenziale condiviso di 2,00 USD al mese, che limita le prenotazioni dell’app
senza garantire il totale della fattura Google. La generazione resta disattivata per impostazione predefinita.
Consulta [comportamento e limiti](docs/ai-briefs.md).

Documentazione: [Architettura e funzionalità](docs/architecture.md) · [Sviluppo e test](docs/development.md) · [Autenticazione e permessi](docs/authentication.md) · [Distribuzione e database](docs/deployment.md) · [Rassegna AI e budget](docs/ai-briefs.md)

Distribuito con [licenza MIT](LICENSE). Le risorse di terze parti mantengono le rispettive licenze.
