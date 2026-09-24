# How the site updates itself

Nobody approves updates by hand. Robots (GitHub Actions, free) read the official
sources, write the plain-Spanish text, check everything, and publish. If a check
fails, nothing is published and you get an issue plus GitHub's failure email.

## What runs when (times in New York, ET)

| When | Workflow | What it does | What it writes |
|---|---|---|---|
| Mon 5:00 am | `camara.yml` | Pulls every deputy's attendance, committees and bills from the Cámara SIL | `provincias.json` |
| Tue 6:00 am | `senado.yml` | Reads new Senate actas (PDF), totals only, 2 min between downloads | `sesiones.json` |
| Wed 6:00 am | `leyes.yml` | SIL bill status changes and newly passed bills; new laws from the Consultoría | `leyes.json`, `vigencia.json` |
| 2nd, 11th, 27th, 9:00 am | `dinero.yml` | Inflation, unemployment, growth, debt and average salary from official Excel files | `finanzas.json` |
| Daily 7:00 am | `escribir.yml` | One AI writes plain Spanish. A different AI checks it. Only fully passed text is published. | `resumenes.json` |
| Sun 8:00 am | `frescura.yml` | Stale data, broken links (including "página no encontrada" pages), live site vs `main` | issues only |
| By hand | `sonda.yml` | One request per source from a GitHub runner, plus one AI call. Run this first. | nothing |

Times are fixed in UTC by GitHub, so each run happens one hour earlier in
winter (after early November) than shown here.

Every publishing workflow runs in one queue (`publicar-main`), so two never
write at the same time. GitHub keeps at most one run waiting in that queue: if
a third one arrives, the waiting one is cancelled. Nothing breaks; it simply
runs again on its next schedule. Each one runs its tests, reads its source, then runs
`scripts/auto/publicar.sh`:
rebase on `main`, write the news item, write "Datos al", run gates G1 to G10, commit.

## How it fails safe

- **Gates decide, not people.** `scripts/gates/run_gates.py` blocks the whole
  commit when anything is wrong: bad shape, impossible totals, a link that is not
  an official domain or did not answer 200, too many changes, deleted items, good
  data replaced with blanks, text not written by the checked AI, party names,
  opinions or people's names, or a date moving backwards.
- **No names of people in robot text.** The writer's code checks and gate G9
  use one shared check (`scripts/auto/comun.py`): any two-word form of a
  deputy's, senator's or official's name ("Omar Fernández" for "Omar Leonel
  Fernández Domínguez"), or a job title followed by a name ("el ministro Juan"),
  blocks the text, even for people not on any list.
- **Money numbers must be believable.** A new money number must stay in a sane
  range and can't jump too far from the last published one (inflation 5
  points, unemployment 3, growth 8, debt 10, salary 15% or RD$15,000 to
  RD$150,000). If it does, `dinero.py` keeps the old number and lists it in an
  `auto-fuente` issue, and gate G3 blocks it again. The inflation reader also
  checks that its column really is the 12-month rate. This catches an official
  Excel file that gained a column.
- **Named Senate votes can never come back by accident.** Gate G2 fails if any
  file under `docs/` holds a senator-by-name vote, or if
  `MOSTRAR_VOTOS_POR_SENADOR` is anything but `false`.
- **One bad item does not stop the rest.** One unreadable acta, one deputy the
  API won't return, or one money file that fails: that item keeps its last good
  value and gets an issue. The others still publish.
- **A dead source never erases data.** An empty or short pull is treated as a
  failure. A single blank field is refilled with its last good value and noted
  in the run log. A whole list or section that comes back empty blocks the
  publish. Only `estado-fuentes.json` is updated, so the site shows the source
  did not answer. The job stays red.
- **The AI fails closed.** Any error, timeout, block, odd answer or failed
  question means that item is not published. The site shows "Resumen en
  preparación" and the official link. After 3 tries it says "Resumen automático
  no disponible". Before each run, a canary test must pass (a known-good sentence
  passes and 3 known-bad ones fail). If it doesn't, the run stops. If one model
  is down, the next one in `config/ia.json` is tried. Only models listed there
  can publish, so test-stub text can never reach the site (gate G8).
- **Honest dates.** Each section shows "Datos al …", the newest date in the data
  itself, not the day the robot ran.

## One-time setup (the only human steps)

1. Run **Sonda** once (Actions tab, then Run workflow). It shows which sources a
   GitHub runner can reach. Only the Cámara SIL has been proven so far.
2. Add the secret **`GEMINI_API_KEY`**. Use a free AI Studio key from a project
   the site owns, with no billing attached. On the free tier, Google may use
   what we send to improve its products. That is fine here: we only send public
   official texts. The free daily limit is shown only inside AI Studio.
   Unverified: whether a busy day (several hundred check questions) fits in it.
   If the limit is hit, the rest of the items fail closed and retry the next
   day. GitHub Models no longer works: it
   answers "OK" with no model behind it (tested 2026-09-24).
3. Set the repo variables **`PSRD_AUTOPUBLICAR = si`** and **`PSRD_IA = si`**.
   Until you do, every workflow runs in dry-run mode: it checks everything,
   publishes nothing, and saves the would-be change as a run artifact.
4. Close PR #4. `camara.yml` replaces it. The fixed Cámara period label and the
   deputy it could not match (Jorge Frías, now matched by his SIL ID) are fixed
   in code. The live site still shows the old label until the first real
   `camara.yml` run with `PSRD_AUTOPUBLICAR = si`.

## Kill switch and undo

- **Stop all publishing:** set `PSRD_AUTOPUBLICAR` to anything but `si`.
- **Stop only the AI:** set `PSRD_IA` to anything but `si`.
- **Undo a batch:** every robot commit is titled `auto(<source>): … [run N]`.
  Run `git revert <commit>` on it.

## Where to look

- **Issues:** `publicacion-bloqueada` (a gate stopped a commit),
  `auto-fuente` (items kept at their old value), `datos-viejos` (stale source,
  stopped robot, broken links, site out of sync), `auto-resumen` (AI text that
  failed review). Each issue closes itself once the problem is gone.
  Links that block robots (HTTP 403/429) or whose server omits part of its
  certificate are only logged, not reported as broken: a robot can't tell
  whether a person can open them.
- **Artifacts:** each run keeps its log (`.psrd-run/`) for 30 days. That
  includes receipts, gate results, the rejected AI drafts and the diff.
- **Tests:** `python -m pytest -q tests`. They use saved real responses from
  each source in `tests/fixtures/`.
