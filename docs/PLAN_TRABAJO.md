# Plan de trabajo — reducir el uso NO CONSENTIDO de fotos (más allá del entrenamiento)

Objetivo amplio: reducir el uso no consentido de fotografías en distintos escenarios. Métricas SEPARADAS por objetivo; nunca afirmar "protegida contra todos los modelos comerciales".

## Orden de ejecución (fijado por la usuaria 2026-10-17)

### 1. Protección contra entrenamiento — EN CURSO
- [en curso] Ajuste de calidad: barrido ε + JND, medir eficacia (efecto neto), PSNR, LPIPS, robustez JPEG, coste/img. (`unlearnable_quality.py`)
- [ ] Comparar C3 (robust unlearnable) cuando sea viable en CPU.
- [ ] Determinar configuración con efecto medible + calidad aceptable. NO integrar función hasta definir el alcance con precisión.

### 2. Face-swaps y deepfakes — AUDITAR Y FORTALECER
- [x] Auditado: 'rompe identidad' en 4 reconocedores → atacados 7-8/8, no vistos 3-4/8. Proxy (no deepfake real). Solo retratos estudio. No universal.
- [x] Face-swap REAL end-to-end VALIDADO (fp32, SHA256 verificado): control funcional OK (swap transfiere identidad 0.81, reconocedor no visto); con foto protegida el deepfake NO se parece a la persona (0.81→-0.02, 8/8). fp16 era la causa del fallo (comprobado). Límites: 8 retratos estudio, 1 generador, 1 reconocedor no visto.
- [ ] Pruebas con herramientas y casos distintos, con originales como control.

### 3. Reconocimiento biométrico y seguimiento entre imágenes — SEPARADO
- [ ] Reducir identificación facial y la vinculación de distintas fotos de la misma persona.
- [ ] Modelos/datos autorizados; métricas de identificación y falsos positivos.
- [ ] CPU, calidad visual aceptable.

### 4. Privacidad antes de publicar — IMPLEMENTADA Y VERIFICADA (2026-10-17)
- [x] Flujo 100% LOCAL en el navegador (canvas), la foto NO sale del dispositivo. `lib/privacy.ts`, `PrivacyStudio.tsx`, `PrivacySection.tsx`. Sin llamadas de red (verificado por código).
- [x] Elimina EXIF/GPS/fecha: verificado en el ARCHIVO descargado real (imagen con GPS → copia sin GPS ni EXIF). Lector JS detecta y muestra qué contiene el archivo.
- [x] Redacción: difuminar/pixelar/cubrir zonas; verificado que la zona cubierta cambia en el archivo.
- [x] Detección de rostros (FaceDetector del navegador, best-effort con aviso honesto); recorte/resolución.
- [x] Exportación segura: original intacto (verificado), copia nueva; exportProtected falla si quedan metadatos.
- [x] Transparencia: panel "qué se elimina / qué riesgos siguen"; sin mensajes de "100% protegido".

### 5. Comparación y expediente de evidencias — IMPLEMENTADO Y VERIFICADO
Utilidad COMPLEMENTARIA, **100% local**: cuando una copia ya circula, comparar la imagen que encuentres con tus registros y organizar evidencias. `lib/reuse.ts` (núcleo puro), `reuseImage.ts` (huellas con canvas), `reuseStore.ts` (IndexedDB), `EvidenceStudio.tsx`, `EvidenceSection.tsx`.
- [x] Registro local: SHA-256 + pHash (DCT) + dHash + miniatura; solo huellas, nunca la foto completa; registrar/consultar/eliminar.
- [x] Comparación: SHA-256 (idéntico) + hash perceptual (similitud, umbrales calibrados) + recalculado de integridad. Sin red (solo `blob:` en memoria).
- [x] Datos de la publicación (declarados por el usuario; la app no verifica URL/fecha) + expediente descargable (HTML imprimible + JSON) con huellas, método, resultado, adjuntos, limitaciones y pasos.
- [x] Calibración MEDIDA (`tests/reuse_perceptual.test.py`): recompresión y reescalado se detectan; recortes fuertes NO (limitación). Pruebas Node (`tests/reuse.test.mjs`) + flujo completo verificado en navegador; cero peticiones de red.
- Alcance honesto: no es un buscador de Internet (tú aportas las imágenes); una coincidencia no prueba infracción; el expediente no garantiza admisibilidad legal. Ver `docs/EVIDENCIAS.md`.

### Descartado: búsqueda facial inversa propia (2026-10-18)
Se exploró y construyó un motor propio de búsqueda facial (MTCNN+FaceNet, índice vectorial, rastreador recursivo) y una búsqueda web asistida (abría Google/Yandex/Bing/TinEye). **Retirado del producto por decisión de la usuaria.** Razones honestas: (1) sin indexar la fuente no hay dónde buscar — no es funcional como un "PimEyes" (cobertura de todo internet = infraestructura de data-center, no un algoritmo; y PimEyes/FaceCheck/Lenso ya existen, de pago); (2) un buscador facial de cualquier persona es terreno legal delicado (biométrico, GDPR, caso Clearview AI) y contradice la misión del proyecto. Se eligió **enfocar en lo local, funcional y propio**. Código eliminado del repo (`engine/search/`, `FaceSearchPanel`, `WebSearchPanel`, `searchEngine.ts`, `reuseSearch.ts`).

Nombre del proyecto: **Image Privacy Toolkit** (antes "Velo", ya existía). Variables de entorno internas (VELO_*) y la caché del motor se mantienen por compatibilidad.

## Principios
- Implementar experimentos viables con pruebas reproducibles; registrar resultados reales.
- Si una técnica falla, documentar por qué y evaluar alternativa.
- Métricas separadas por objetivo. Sin promesas de protección universal.
