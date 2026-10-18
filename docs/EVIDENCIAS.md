# Comparación y expediente de evidencias

## Por qué existe

Las protecciones preventivas (perturbación, limpieza de metadatos) tienen límites y no pueden impedir todos los usos no consentidos de una fotografía. Cuando una copia **ya circula**, esta función aporta una utilidad complementaria: comparar imágenes y **organizar evidencias** de forma sencilla, local y verificable, para que quien lo necesite pueda documentar un caso y consultar los cauces de reporte de la plataforma correspondiente.

No inventa la huella digital de imágenes (es una técnica conocida). Su valor está en integrar registro, comparación y documentación en un solo flujo **100% local** (sin GPU ni servicios externos). **No es un buscador de Internet**: tú aportas las imágenes a comparar.

## Qué hace

1. **Registro local de fotografías.** Guardas un nombre de referencia, el SHA-256 del archivo, dos huellas perceptuales (pHash y dHash), la fecha de registro, notas y una miniatura pequeña. Se guardan **solo las huellas y la miniatura, nunca la foto completa**, en el navegador (IndexedDB).
2. **Comparación con una imagen que encuentres.** Importas otra imagen y se compara con tus registros por SHA-256 (idéntico byte a byte) y por hash perceptual (parecido visual tras reescalado o recompresión). El resultado es comprensible: *archivo idéntico*, *similitud alta*, *posible similitud (revisar)* o *sin coincidencia*. Ocurre en tu navegador; ninguna imagen sale del dispositivo (solo se usa una URL `blob:` en memoria).
3. **Datos de la publicación.** Añades la URL, la plataforma, cuándo la encontraste y por qué crees que no se autorizó. **La app no abre ni verifica** la URL, la fecha ni el contenido: quedan marcados como *declarados por ti*.
4. **Expediente descargable.** Generas un informe en **HTML imprimible** (con las imágenes embebidas) y en **JSON** estructurado, con el identificador del caso, las huellas SHA-256, el resultado y el método de comparación, los datos de la publicación, los adjuntos, las advertencias y una lista de pasos sugeridos.

## Privacidad y almacenamiento

- Registro y comparación 100% locales; sin APIs ni servicios externos.
- El registro vive en IndexedDB **de este navegador**; se puede perder si borras los datos del sitio. No se sincroniza ni sale del equipo.
- Se guardan huellas y una miniatura reducida, no la fotografía original.
- Puedes **eliminar** cualquier registro (se borra también de IndexedDB).

## Integridad

El SHA-256 permite **recalcular** la huella de un archivo y comprobar si cambió. Esto verifica la integridad de los archivos disponibles; **no demuestra** cuándo existían, quién los creó ni quién posee los derechos. Las fechas de registro y de generación las anota la aplicación: son *declaradas/registradas por la app*, no una prueba independiente.

## Alcance del método (calibración medida)

Calibración sobre 6 retratos de prueba (distancia de Hamming del pHash, 0–64; menor = más parecido). Umbrales: similitud alta ≤ 10, posible ≤ 18. Reproducible con:

```bash
services/engine/.venv/bin/python apps/web/tests/reuse_perceptual.test.py
```

| Transformación | Distancia media | Máx | ¿Se detecta? |
|---|---|---|---|
| Recompresión JPEG (q90 / q60 / q40) | 0.0 | 0 | **Sí** |
| Reescalado 50 % y 150 % | 0.0 | 0 | **Sí** |
| Recorte leve (5 % por lado) | 13.0 | 18 | En el límite |
| Recorte fuerte (20 % por lado) | 31.0 | 36 | **No** (limitación) |
| Rotación 3° | 10.0 | 16 | En el límite |
| Entre imágenes **distintas** | 28.7 | mín 20 | No coinciden (sin falsos positivos) |

**Lectura honesta:**

- Detecta bien **recompresión y reescalado** (el caso más común de reutilización): distancia ≈ 0.
- **No detecta** recortes fuertes ni, de forma fiable, rotaciones: son una limitación conocida de los hashes perceptuales globales.
- Las imágenes distintas quedan lejos (mín. 20 > umbral 18), pero el margen es ajustado: por eso la banda 10–18 se etiqueta **«posible, revisar»** y nunca como prueba. Un recorte leve puede caer en esa banda y confundirse con una imagen parecida.
- La **comparación** se limita a las imágenes que tú aportas: **no es un buscador** de Internet.

## Lo que un expediente NO es

- Una coincidencia **no demuestra** copia, titularidad, identidad ni uso ilícito.
- El expediente **organiza** evidencias que tú aportas; **no garantiza** su admisibilidad legal ni emite conclusiones legales.
- Para decisiones legales, busca orientación de una persona con conocimientos en tu jurisdicción.

## Pruebas automatizadas

- `apps/web/tests/reuse.test.mjs` (Node): SHA-256 exacto, robustez del pHash ante ruido/reescalado simulados, ausencia de falsos positivos, veredictos, generación y validación del expediente (con escape de HTML), recalculado de integridad y ausencia de red en el código.
- `apps/web/tests/reuse_perceptual.test.py` (Pillow): reimplementa el mismo pHash/dHash, **verifica que coincide bit a bit con el código TS** y mide el comportamiento ante transformaciones **reales** (la tabla de arriba).
- Flujo completo verificado en navegador real: registrar → comparar (copia recomprimida y reescalada → *similitud alta*; imagen distinta → *sin coincidencia*) → datos de la publicación → descargar expediente (HTML + JSON); manejo de imágenes corruptas y formatos no admitidos; eliminación de registros; **cero peticiones de red**.
