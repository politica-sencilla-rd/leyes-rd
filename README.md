# Política Sencilla RD — Fácil de Entender

A free, no-login static website that explains Dominican Republic politics — laws,
provinces, Senate sessions, and public money — in plain, kid-friendly Spanish,
grouped by sector, with expandable detail, vote records, and a province view of
leaders.

Live: https://politica-sencilla-rd.github.io/leyes-rd/

Built 2026-06-07 by Lawyer (under Kelvin's explicit override).

## What works now (v0)
- Sector-grouped law list (Salud, Trabajo, Seguridad, Educación). Never by title/ID.
- Tap a sector -> tap a law -> expands to "¿Qué es?", "¿Por qué se propuso?", and "¿Quién votó?".
- Province tab: tap a province -> see leaders, party, plain summary, and vote record.
- Kid-simple Spanish, mobile-first, fun UI.
- Pure static: index.html + styles.css + app.js + /data/*.json. No backend.

## IMPORTANT — data is SAMPLE only
Everything in /data/leyes.json and /data/provincias.json is clearly labelled
"DATOS DE EJEMPLO". These are NOT real laws or real votes. A yellow banner says so.
Do not present this as real until the live feed is wired. Honesty first — no fake laws
shown as real.

## Files
- index.html — page shell + tabs
- styles.css — flag-colored, kid-friendly theme
- app.js — loads JSON, groups by sector, expand logic, province profiles
- data/leyes.json — sample laws grouped by sector
- data/provincias.json — sample provinces + leaders

## Run locally
Must use a web server (fetch() won't work from file://):
    cd site && python3 -m http.server 8765
Open http://127.0.0.1:8765

## Deploy free on GitHub Pages
1. Create a public repo (e.g. leyes-rd).
2. Put the contents of /site at the repo root.
3. Repo Settings -> Pages -> Source: main branch, / (root).
4. Live at https://<user>.github.io/leyes-rd/

## Next steps (the real work)
1. DATA PIPELINE: a scheduled GitHub Action that pulls bills from the Senate SIL and
   Chamber SIL, then rebuilds data/leyes.json. "Real-time" on static = scheduled rebuild.
2. PLAIN-LANGUAGE STEP: bills are written in legalese. Need an AI summarization pass to
   produce the short "qué es / por qué" Spanish text per law.
3. VOTING RECORDS — OPEN RISK: per-legislator votes are NOT cleanly published by the DR
   congress. Confirm what vote data is actually obtainable before promising this feature.
4. Real province + leader data (from JCE / congress rosters).
5. Optional: real clickable SVG map instead of the province grid.

Spec: 2026-06-07-spec.md

## Cómo colaborar

No necesitas saber programar para aportar — solo traer un dato con su fuente
oficial. La regla del proyecto es simple: **sin fuente oficial, no entra.** Lee la
guía completa en [CONTRIBUTING.md](CONTRIBUTING.md): cómo reportar un error, sugerir
una mejora o traer una nueva fuente de datos, cómo se revisa cada aporte contra
fuentes oficiales antes de publicarse, y cómo **hacer tu propia copia en vivo del
sitio** (un fork + GitHub Pages, en minutos) para que esta información nunca dependa
de un solo sitio.

## Licencia

Este proyecto es de código abierto y gratis para siempre.

- El código (TypeScript, HTML, CSS) está bajo licencia MIT. Lo puedes copiar,
  cambiar y usar para lo que quieras. Ver el archivo LICENSE.
- Los textos y los archivos de datos del sitio los puedes copiar y volver a
  publicar, siempre que des crédito al proyecto (licencia CC BY 4.0).
- Los hechos de fondo (leyes, votaciones, presupuestos) vienen de fuentes
  oficiales del gobierno y son información pública: nadie es dueño de ellos.

En pocas palabras: cualquiera puede revisar la receta completa, copiarla y
volver a publicarla. Solo pedimos que, si republicas los textos o los datos,
digas de dónde salieron.
