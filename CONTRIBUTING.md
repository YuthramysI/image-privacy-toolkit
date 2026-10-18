# Contribuir a Image Privacy Toolkit

Gracias por tu interés. Este proyecto es **software libre y, en su parte de perturbación, investigación abierta**. Se contribuye de tres formas, y las tres valen:

1. **Código** — arreglar errores, mejorar la interfaz, la accesibilidad o el motor.
2. **Investigación** — diseñar, correr y publicar experimentos (incluidos los que fallan).
3. **Documentación y pruebas** — aclarar, traducir, añadir casos de prueba o datos con licencia libre.

El principio que gobierna todo: **honestidad medible**. No se añade ninguna afirmación de eficacia sin una prueba o una medición reproducible que la respalde. Un resultado negativo bien hecho es tan valioso como uno positivo.

---

## Antes de empezar

- Mira las [preguntas abiertas de investigación](docs/PREGUNTAS_ABIERTAS.md) y la [matriz de investigación](docs/MATRIZ_INVESTIGACION.md): dicen qué está demostrado, qué falla y qué está sin probar.
- Para algo no trivial, abre una *issue* primero y describe qué quieres hacer. Así evitamos trabajo duplicado y afinamos el enfoque.
- Lee [docs/LIMITACIONES.md](docs/LIMITACIONES.md): define qué promete el proyecto y qué no. Las contribuciones no pueden contradecir ese marco sin evidencia.

---

## Contribuir con código

### Preparar el entorno

```bash
# Web (interfaz + privacidad local; no necesita el motor)
cd apps/web
npm install
npm run dev            # http://localhost:3000

# Motor de perturbación (opcional; la primera vez descarga ~1 GB de modelos)
cd services/engine
make dev
make serve             # http://localhost:8000
```

### Antes de abrir un *pull request*

Deben pasar las tres comprobaciones de la web:

```bash
cd apps/web
npm run lint
npx tsc --noEmit
npm test
```

Y, si tocaste el motor, sus pruebas:

```bash
cd services/engine
.venv/bin/pytest
```

### Estilo

- Sigue el estilo del código que ya existe (nombres, formato, estructura). No reformatees archivos enteros en un PR que arregla otra cosa.
- La interfaz está en **español**; mantén ese idioma en textos de cara al usuario.
- Accesibilidad: respeta `prefers-reduced-motion`, usa `:focus-visible`, estados ARIA correctos. No rompas la navegación por teclado.
- Privacidad por diseño: **ninguna función de privacidad local o de comparación puede introducir una llamada de red.** Si tu cambio añade una petición, no se acepta en esos flujos.
- No incluyas fotografías privadas, claves, tokens ni modelos de gran tamaño en el repositorio.

---

## Contribuir con investigación

Aquí está el mayor espacio para aportar. El objetivo es avanzar (o refutar) las [preguntas abiertas](docs/PREGUNTAS_ABIERTAS.md) con método.

### Un experimento válido necesita

1. **Control limpio** + **control de ruido aleatorio** del mismo tamaño (ε). Se reporta el **efecto neto** (protegido vs aleatorio), no solo protegido vs limpio.
2. **Modelo no visto** como juez (no usado para generar la perturbación).
3. **Transformación realista** antes de evaluar (reescalado + JPEG): simula subir la foto a una red.
4. **Criterio de éxito/fracaso escrito antes** de ver los resultados.
5. **Calidad perceptual medida** (PSNR, LPIPS): di si la protección es visible o no.
6. **Reproducible** (≥2 semillas) con el comando exacto.

Un experimento sin control aleatorio o sin modelo no visto no se acepta como evidencia, por buenos que parezcan los números.

### Dónde va el código de investigación

- Experimentos exploratorios: `services/engine/engine/research/`.
- Evaluación y benchmark: `services/engine/engine/eval/`.
- Cada experimento nuevo añade su resultado —positivo o negativo— a [docs/MATRIZ_INVESTIGACION.md](docs/MATRIZ_INVESTIGACION.md), con fecha, controles y limitaciones.

### Datos

- Usa datasets con **licencia libre o consentimiento explícito**, y documenta la procedencia y sus límites (como se hace con Olivetti y las imágenes NASA de dominio público).
- Nunca subas fotos de personas sin permiso.

---

## Datos sensibles y ética

Este proyecto trata sobre privacidad. Se rechazará cualquier contribución que:

- Añada reconocimiento o búsqueda facial de terceros (es terreno legal delicado —biométrico, GDPR— y contradice la misión; ver la nota en [docs/PLAN_TRABAJO.md](docs/PLAN_TRABAJO.md)).
- Prometa protección o anonimato "garantizado" / "100%".
- Envíe fotos del usuario a servicios externos en los flujos locales.
- Incluya datos personales reales en el repositorio o en las pruebas.

---

## Licencia de tus contribuciones

Al contribuir, aceptas que tu aportación se publique bajo la **[Licencia MIT](LICENSE)** del proyecto. Los modelos preentrenados y datasets de terceros conservan su propia licencia (ver [LICENSING.md](LICENSING.md)); no mezcles en el código funciones que dependan de modelos no comerciales sin marcarlo claramente.

---

## Reportar un error

Abre una *issue* con: qué esperabas, qué ocurrió, pasos para reproducirlo, y tu entorno (navegador/SO, o versión de Python para el motor). Para un fallo de seguridad o privacidad, indícalo en el título para priorizarlo.
