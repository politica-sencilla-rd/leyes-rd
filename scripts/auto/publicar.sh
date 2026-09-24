#!/usr/bin/env bash
# Shared publish step for every data workflow:
#   rebase -> Novedad (templates) -> "Datos al" -> gates G1-G10 -> commit -> push.
# No human approves anything: the gates decide. Any gate failure = nothing is
# pushed, the job goes red (GitHub's failure email) and one issue is updated.
#
#   bash scripts/auto/publicar.sh <familia>            normal run
#   bash scripts/auto/publicar.sh <familia> --fallo    the source failed: publish ONLY
#       estado-fuentes.json (so the site and the freshness check see the failure),
#       then exit 1 so the job stays red.
# Kill switch: repo variable PSRD_AUTOPUBLICAR must be "si"; anything else = dry
# run (everything runs, nothing is committed; the diff is kept as an artifact).
set -euo pipefail
FAMILIA="${1:?familia}"
MODO="${2:-}"
cd "$(git rev-parse --show-toplevel)"
mkdir -p .psrd-run

git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

if [ "$MODO" = "--fallo" ]; then
  git checkout -- docs/data docs/novedades.xml pipeline-state scripts/diputados_stats.json config 2>/dev/null || true
  git clean -fdq -- docs/data pipeline-state || true
fi

# Our changes sit on top of the newest main (another workflow may have pushed).
ANTES=$(git stash list | wc -l)
git stash push --include-untracked -q -- docs pipeline-state scripts/diputados_stats.json config || true
git pull -q --rebase origin main
if [ "$(git stash list | wc -l)" -gt "$ANTES" ]; then
  git stash pop -q || { echo "conflicto al reaplicar los cambios sobre main: no se publica"; exit 1; }
fi

[ "$MODO" = "--fallo" ] || python3 scripts/auto/novedades.py
python3 scripts/auto/novedades.py --solo-xml
python3 scripts/auto/datos_al.py

gates() { python3 scripts/gates/run_gates.py --base-ref origin/main; }
if ! gates; then
  python3 scripts/auto/issues.py abrir --clave "bloqueo-$FAMILIA" --etiqueta publicacion-bloqueada \
    --titulo "[auto] Publicación bloqueada: $FAMILIA" --cuerpo-archivo .psrd-run/gates.log || true
  echo "Los controles bloquearon la publicación. No se sube nada."
  exit 1
fi
python3 scripts/auto/issues.py cerrar --clave "bloqueo-$FAMILIA" --etiqueta publicacion-bloqueada || true

git add docs/data docs/novedades.xml pipeline-state scripts/diputados_stats.json config
git diff --cached --stat | tee .psrd-run/cambios.txt
git diff --cached > .psrd-run/cambios.patch || true

if [ "${PSRD_AUTOPUBLICAR:-}" != "si" ]; then
  echo "Interruptor PSRD_AUTOPUBLICAR apagado: corrida en seco, no se sube nada (ver el artefacto)."
  git reset -q
  [ "$MODO" = "--fallo" ] && exit 1
  exit 0
fi

if git diff --cached --quiet; then
  echo "Nada cambió."
else
  RESUMEN="$(python3 -c "import json;r=json.load(open('.psrd-run/resumen.json'));print('; '.join(f'{k}: {v.get(\"estado\")}' for k,v in r['fuentes'].items()))" 2>/dev/null || echo "$FAMILIA")"
  git commit -q -m "auto($FAMILIA): $RESUMEN [run ${GITHUB_RUN_ID:-local}]"
  if ! git push -q origin HEAD:main; then
    git pull -q --rebase origin main
    gates || { echo "Los controles fallaron tras el segundo rebase: no se sube nada."; exit 1; }
    git push -q origin HEAD:main
  fi
  echo "Publicado."
fi
[ "$MODO" = "--fallo" ] && exit 1
exit 0
