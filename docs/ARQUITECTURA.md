# Arquitectura de Image Privacy Toolkit — cuatro módulos

El proyecto se organiza en cuatro módulos independientes. Estado a 2026-10-18.

## 1. Registro de consentimiento y derechos — HECHO

`engine/registry.py`. Para cada imagen genera un certificado firmado y verificable que deja constancia de que el titular no autoriza el uso para IA.

- Hash **SHA-256** de la imagen original y de la protegida.
- Declaración explícita de no autorización (entrenamiento, usos generativos, minería, extracción de identidad/descripciones/etiquetas).
- Titular, fecha (UTC) e identificador de la marca de agua.
- Firma **Ed25519** sobre todo lo anterior; la clave pública viaja en el registro, así que cualquiera puede verificarla. Alterar un solo campo invalida la firma (probado).
- API: `GET /jobs/{id}/record`. CLI: `python -m engine.registry create|verify`.

## 2. Motor de perturbación — EN CURSO

`engine/protect/`. Módulos independientes por tipo de protección:

- **Rostro** (`face.py`): ataca a los reconocedores faciales (ArcFace, FaceNet). Rompe el face-swap 8/8. HECHO.
- **Edición** (`vae.py`): ataca a los encoders de difusión abiertos (Stable Diffusion, FLUX). Efecto modesto; mejora pendiente.
- **Extracción de etiquetas, descripciones y representaciones** (`research/transfer_lab.py`, **línea cerrada — resultado negativo**): se investigó atacar los codificadores de visión (CLIP) que usan los VLM. En los *proxies* abiertos, atacar **capas intermedias** (ILA) transfería +76% mejor a un modelo no visto que atacar el embedding final. Pero al **probarlo directo en Gemini, esa mejora NO se tradujo en ninguna degradación real** de la descripción: la métrica proxy no predice a un modelo cerrado, y la línea se cerró (ver [INVESTIGACION_TRANSFERENCIA.md](INVESTIGACION_TRANSFERENCIA.md) y la pregunta abierta B3 en [PREGUNTAS_ABIERTAS.md](PREGUNTAS_ABIERTAS.md)). `research/assistant_shield.py`, `label_shield.py` y `caption_lab.py` quedan como registro de esos experimentos.

Presupuesto perceptual común: `budget.jnd_eps_map` (modelo JND) reparte el ruido fuera de la piel lisa → ~37% más invisible (LPIPS) manteniendo la eficacia.

## 3. Evaluador de modelos cerrados — EN CURSO

`engine/eval/`. Mide la eficacia **después** de JPEG y reescalado (una subida real a redes), siempre contra modelos que el ataque no vio.

- `faceswap.py`: identidad ArcFace (el de roop/FaceFusion) + uno no visto.
- `assistants.py`: edición en la API de Gemini, bajo condiciones reproducibles y solo con imágenes autorizadas (retratos de dominio público). La capa gratuita no cubre edición de imagen; se mide manualmente o con facturación activada.
- `run.py` / `summary.py`: visibilidad (PSNR/SSIM/LPIPS) y daño al latente de difusión.

Principio: nunca se envían imágenes sin permiso; las pruebas son reproducibles y se publican, funcionen o no.

## 4. Exportación — HECHO

`engine/seal.py` + `engine/metadata.py`. La imagen protegida se descarga con:

- la **perturbación**;
- la **marca de agua invisible** (TrustMark, Adobe/MIT), que sobrevive a reescalado y JPEG 75 (probado);
- **metadatos de derechos** (IPTC) y **credenciales C2PA** firmadas con la declaración de que el entrenamiento generativo y otros usos están prohibidos;
- su **registro de derechos** (módulo 1) como archivo `.json` aparte.

Verificación: `POST /verify`, `python -m engine.seal <img>`, `python -m engine.registry verify`.

## Nota de honestidad

Ninguna capa garantiza que un modelo no use la foto; menos aún los modelos grandes cerrados, donde frenar la edición con perturbación invisible sigue siendo un problema de investigación abierto. Lo que el conjunto sí logra: proteger de verdad contra el face-swap, degradar a los modelos abiertos, y dejar constancia firmada y verificable de que no hubo consentimiento. Todo se mide y se publica.
