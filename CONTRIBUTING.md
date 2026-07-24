# Cómo colaborar con Política Sencilla RD

Gracias por querer ayudar. Este sitio existe para que cualquiera entienda la política dominicana sin enredos. Mejora con la gente, no en contra de ella.

No necesitas saber programar para aportar. Lo que de verdad necesitas es **una fuente oficial que cualquiera pueda revisar.**

## La regla más importante: sin fuente oficial, no entra

Todo lo que el sitio muestra sale de una fuente oficial del Estado dominicano: el Senado, la Cámara de Diputados, la Junta Central Electoral (JCE), el Banco Central, los ministerios, la Gaceta Oficial, los ayuntamientos.

Nada se inventa. Nada entra "porque alguien lo dijo". Si un dato no se puede verificar en una fuente oficial con un enlace, no se publica.

Esa regla es la que mantiene fuera el ruido y el fanatismo. No publicamos opiniones de la calle ni rumores de partido. Publicamos hechos que tú mismo puedes comprobar.

## Cómo se piensa cada aporte: un dato + el enlace oficial

No importa si vienes a arreglar un error o a traer datos nuevos. Todo aporte tiene la misma forma:

> Una afirmación que se puede verificar, con el enlace a la fuente oficial.

Aquí están los tres tipos de aporte y cómo se ven:

### 🐛 Vi un error
"El sitio dice X. La fuente oficial dice Y. Aquí está el enlace."

Ejemplo: "La ficha de Santiago dice que el alcalde gana RD$200,000. La nómina oficial del ayuntamiento de enero 2026 dice RD$265,000. Aquí está el enlace al documento."

### 💡 Tengo una sugerencia
Una idea para explicar algo más fácil o agregar algo útil. Si tu idea trae un dato, dinos de dónde sale oficialmente.

### 📚 Conozco una fuente de datos
"Este organismo oficial publica Z. Aquí está dónde lo publica."

Ejemplo: "El Ministerio de Interior y Policía publica las nóminas de los gobernadores en su portal de transparencia. Aquí está el enlace."

## Cómo proponer un cambio

Tienes dos caminos. El primero es para cualquiera. El segundo es para quien sabe programar.

### Camino 1 — Abrir un "issue" (lo más fácil, sin programar)

Un "issue" es solo un mensaje que le dejas al proyecto en GitHub. Es gratis y toma un minuto.

1. Entra a la página de formularios: https://github.com/politica-sencilla-rd/leyes-rd/issues/new/choose
2. Elige el formulario que va contigo (error, sugerencia o fuente de datos).
3. Llena lo que te pregunta. Cada formulario te pide **el enlace a la fuente oficial** si lo tienes.
4. Envíalo. Listo. Nosotros lo revisamos.

### Camino 2 — Mandar un cambio en el código (un "pull request")

Si sabes programar, puedes proponer el cambio ya hecho:

1. Haz un "fork" (tu propia copia) del repositorio en GitHub.
2. Edita los archivos que toque (casi siempre los datos en `docs/data/`).
3. Abre un "pull request" explicando el cambio y citando la fuente oficial.

## Dónde vive cada dato

El sitio es puro: una página, un estilo y archivos de datos. Toda la información está en archivos en `docs/data/`:

- `leyes.json` — las leyes, por tema. Fuente: Senado y Cámara de Diputados.
- `provincias.json` — senadores, diputados, gobernadores, alcaldes y regidores, con su partido. Fuentes: JCE (electos), Senado y Cámara (asistencia, comisiones, iniciativas), nóminas oficiales de transparencia (sueldos).
- `sesiones.json` — las sesiones del Senado y sus votaciones. Fuente: actas del Senado.
- `finanzas.json` — el dinero del país (lo que produce, gana, gasta, debe). Fuentes: Banco Central, DIGEPRES, Ministerio de Hacienda, TSS, ONE.
- `vigencia.json` — las leyes nuevas y desde cuándo mandan. Fuentes: Gaceta Oficial y la Consultoría Jurídica del Poder Ejecutivo.
- `novedades.json` — las mejoras recientes del sitio, escritas fácil.

Cada dato lleva su fuente dentro del propio archivo.

## Cómo se revisa antes de salir en vivo

Ningún aporte sale en vivo de forma automática. El camino es siempre el mismo:

1. Llega tu aporte (un issue o un pull request).
2. Se revisa contra la fuente oficial que trajiste. Si no hay fuente que cualquiera pueda comprobar, no entra.
3. Si pasa, se suma a los archivos de datos y al sitio.
4. Se anota la mejora en `docs/CHANGELOG-improvements.md` y en las Novedades del sitio.

La promesa es simple: **cada aporte se revisa contra fuentes oficiales antes de publicarse.** Así el sitio se mantiene confiable mientras crece con la gente.

## 🌱 Haz tu propia copia

Este sitio es de código abierto y la licencia te da el derecho de copiarlo. Eso no es un detalle: significa que esta herramienta no se puede apagar atacando un solo sitio. Si hay muchas copias, la información está segura.

Hacer tu propia copia en vivo toma minutos y no cuesta nada:

1. Entra al repositorio en GitHub: https://github.com/politica-sencilla-rd/leyes-rd
2. Toca el botón **"Fork"** (arriba a la derecha). Eso crea una copia tuya, con todos los datos incluidos.
3. En tu copia, ve a **Settings → Pages**.
4. En "Source", elige la rama `main` y la carpeta `/docs`. Guarda.
5. En un par de minutos tendrás tu propio sitio en vivo, en `https://TU-USUARIO.github.io/leyes-rd/`.

Ya está. Tienes el sitio completo, idéntico, bajo tu control. Mientras más copias existan, más difícil es que alguien borre esta información del internet.

## Licencia

El código está bajo licencia MIT. Los textos y datos los puedes copiar y volver a publicar dando crédito (CC BY 4.0). Los hechos de fondo (leyes, votaciones, presupuestos) son información pública: nadie es dueño de ellos. Ver `LICENSE`.
