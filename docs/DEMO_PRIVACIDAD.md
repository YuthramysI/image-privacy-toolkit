# Demostración del flujo de privacidad local

Esta es la demostración breve del flujo completo de la versión 1.0: cargar una
foto, aplicar protección, revisar el resultado y descargar una copia procesada.
Todo ocurre en el navegador; la imagen no sale del dispositivo.

## Pasos

1. `cd apps/web && npm install && npm run dev` → abrir `http://localhost:3000/#privacidad`.
2. Arrastrar una foto (JPEG/PNG/WebP) al estudio de privacidad.
3. El panel **«Qué contiene tu archivo»** lista lo que se detectó: GPS en rojo,
   y fabricante, fecha, cámara en ámbar. Se avisa: «Todo esto se eliminará al descargar».
4. Elegir un modo (Difuminar / Pixelar / Cubrir) y arrastrar sobre la foto para
   marcar lo que se oculta (caras, documentos, matrículas). Botón «Detectar
   rostros» como ayuda orientativa.
5. Opcional: limitar la resolución y elegir formato (JPEG/PNG).
6. «Descargar copia privada». El original queda intacto; se descarga
   `nombre-privada.jpg`.

## Verificación ejecutada (2026-10-17)

Se corrió el flujo completo en un navegador real con una foto JPEG de prueba que
**sí tenía GPS y EXIF** y una zona roja marcada para tapar. Resultados medidos
sobre el **archivo descargado** (no sobre el estado de la interfaz):

| Comprobación | Esperado | Medido |
|---|---|---|
| GPS en la copia | ausente | **ausente** |
| EXIF en la copia | ausente | **ausente** |
| Dimensiones | 600×400 (preservadas) | **600×400** |
| Zona marcada (Cubrir) | negra, no recuperable | **100% negra, 0% rojo recuperable** |
| Original en disco | intacto (GPS+EXIF) | **intacto** |
| Peticiones de red durante el flujo | ninguna | **ninguna** |

El tráfico de red de la pestaña se inspeccionó con las herramientas del
navegador durante la exportación: **cero peticiones**. El código del flujo
(`src/lib/privacy.ts`, `src/components/PrivacyStudio.tsx`) no contiene ninguna
llamada `fetch`/XHR/WebSocket.

## Pruebas automatizadas

```bash
cd apps/web
npm test        # readMetadata.test.mjs — detección de EXIF/GPS (3 casos)
# invariante de limpieza (necesita piexif/Pillow; el venv del motor los trae):
../../services/engine/.venv/bin/python tests/privacy_invariant.test.py
```

- `readMetadata.test.mjs`: detecta GPS/EXIF en un JPEG que los tiene y no los
  inventa en archivos que no.
- `privacy_invariant.test.py`: re-codifica como lo hace el navegador una imagen
  con GPS y confirma que el resultado no conserva GPS ni EXIF y preserva la imagen.

Además, `exportProtected` vuelve a leer el archivo generado y **se niega a
descargarlo si aún tuviera EXIF** (verificación del archivo final).

## Qué no hace

Quitar metadatos **no anonimiza**: una cara, un documento o un lugar visibles
pueden seguir identificando. Por eso se ofrecen la redacción y el recorte, y la
detección de rostros se presenta como orientativa, no infalible. Ver
[LIMITACIONES.md](LIMITACIONES.md).
