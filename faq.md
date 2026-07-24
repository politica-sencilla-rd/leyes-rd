# Leyes RD — Project FAQ

Scoped to the DR-laws site project. Plain answers, with the source. Update as we learn more.
Last updated 2026-06-07.

## Voting transparency

Q: Why doesn't the site show who voted on each law?
A: The Congress records the votes but does not publish them openly per legislator. The common (electronic) vote usually shows only the totals; a "nominal" (by-name) vote does record each name. Source: Reglamento de la Cámara de Diputados / Reglamento del Senado.

Q: Are legislators' votes secret in the DR?
A: No. Secret voting in Congress is banned. The "secret vote" in the Constitution refers to CITIZENS voting in elections, not legislators in session. Source: Reglamento de la Cámara (no votación secreta); Constitución Art. 208.

Q: Can we show how each senator voted on a bill?
A: No — confirmed by checking the actual files (2026-06-07). Neither chamber publishes per-person votes. The Senate's "Votaciones Electrónicas" page is empty ("no cuenta con archivos"). The published session minutes (actas) show only the TOTAL per bill (e.g. "25 votos a favor, 27 senadores presentes") plus a separate named attendance list. The per-name electronic tally is referenced in the minutes as "Votación adjunta al acta" but that attachment is not published.

Q: But doesn't the Senate's automated system record each senator's vote?
A: Yes, internally — the system captures an individual record live in the chamber. But that individual record is not published to the public. So it exists, it just isn't shared.

Q: What CAN we get from the official files?
A: Per session: bill names, dates, status, vote TOTALS, and per-senator ATTENDANCE (present/absent). Format: clean text-based PDF minutes with a predictable URL pattern, downloadable with no captcha. Latest acta lags ~5-6 weeks; attendance lists are more current. Scraping totals+attendance = medium difficulty; per-person votes = not online, so impossible to scrape.

Q: And the Chamber of Deputies?
A: Same model, same answer — actas + attendance, no per-deputy vote breakdown published.

Q: How do I request a vote record?
A: Free, under the Free Access to Information law (Ley 200-04), through the SAIP portal (saip.gob.do). Pick the chamber, ask for the "acta de votación nominal" for the bill/date. They must answer in ~15 working days.

Q: Does the US publish individual votes?
A: Yes. Each member's recorded vote is public by law (Constitution, Article 1, Section 5) and posted at congress.gov and the House/Senate sites.

Q: Who watches the DR Congress?
A: Participación Ciudadana (main transparency watchdog), the Observatorio Político Dominicano (has a legislative unit), and the Red Latinoamericana por la Transparencia Legislativa.

## Data on the site

Q: Where do the laws come from?
A: Real bills from the Senate's own 2024-2028 database (senado.gov.do / senadord.gob.do), rewritten into simple Spanish and grouped by sector.

Q: Are the laws real?
A: Yes. Earlier versions used clearly-labeled samples; the live site now uses real Senate bills.

Q: Why do some laws say "Razón no indicada"?
A: The Senate's bill page lists the title and status but not a written reason, so we don't invent one.

Q: Are the province leaders real?
A: Senators and deputies per province are being filled in from the Senate and Chamber of Deputies (2024-2028). Any province not yet confirmed shows "Información por publicar" — no invented names.

## Build / tech

Q: Where does it live?
A: GitHub Pages (free), repo politica-sencilla-rd/leyes-rd, served from /docs. Live: https://politica-sencilla-rd.github.io/leyes-rd/

Q: What is it built with?
A: TypeScript (src/app.ts compiled to docs/app.js), plain HTML/CSS, JSON data files. No backend.
