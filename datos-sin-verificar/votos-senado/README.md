# Votos por senador — pausados hasta verificarlos

Estos archivos NO se publican: están fuera de `docs/` (la carpeta que sirve GitHub Pages).

- `votos_por_sesion.json` — antes en `docs/data/votos_por_sesion.json` (Sesiones: "Cómo votó cada senador").
- `votos_por_senador.json` — los campos `votos` y `votos_nota` de cada senador, sacados de `docs/data/provincias.json` (ficha: "Registro de votos"). Clave: `provincia` + `nombre`.

Por qué: las listas se leyeron de la pantalla de votación que sale en las transmisiones, no del Senado. Al compararlas con el acta oficial, 2 de 4 proyectos no coinciden (ej.: acta 0106 dice que Antonio Taveras votó en el proyecto 01417; la lista lo muestra "Ausente"). Decisión de Kelvin, 2026-09-24: ocultarlas todas hasta revisar cada una contra su acta.

Para volver a mostrar una lista ya verificada:
1. Devuelve el archivo a `docs/data/` (y los `votos` a cada senador en `provincias.json`).
2. Pon `MOSTRAR_VOTOS_POR_SENADOR = true` en `src/app.ts` y corre `npm run build`.
3. Muestra solo lo que coincide con el acta; di de dónde sale cada lista.
