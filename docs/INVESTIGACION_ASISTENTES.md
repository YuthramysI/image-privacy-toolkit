# Investigación: asistentes cerrados y face-swap

Objetivo que se investigó: que una foto protegida no pueda usarse para editar o suplantar a la persona sin su consentimiento, ni con asistentes cerrados (Gemini, ChatGPT) ni con herramientas abiertas de face-swap (roop, FaceFusion).

> **Estado (actualizado 2026-10-18).** Dos resultados distintos:
> - **Face-swap (abierto): funciona** — la capa de rostro rompe la identidad de extremo a extremo con un reconocedor no visto (ver [MATRIZ_INVESTIGACION.md](MATRIZ_INVESTIGACION.md)).
> - **Asistentes cerrados (Gemini/ChatGPT) con perturbación invisible: NO funciona** — esta línea se **cerró como resultado negativo**: probado directo en Gemini, la mejora en los proxies no se tradujo en ninguna degradación real (ver la conclusión en [INVESTIGACION_TRANSFERENCIA.md](INVESTIGACION_TRANSFERENCIA.md)). Lo que sigue abierto está descrito, sin prometer nada, en [PREGUNTAS_ABIERTAS.md](PREGUNTAS_ABIERTAS.md) (B3).
>
> Este documento se conserva como **registro de investigación**: la revisión de literatura, las mediciones y las hipótesis que se intentaron. No describe funciones activas del producto contra asistentes cerrados, porque no las hay.

## Dónde estamos (medido)

| Prueba | Resultado |
|---|---|
| Gemini, "mantén el rostro y ponle lentes de sol" | Editó la foto protegida sin problema (prueba manual, 2026-10-16) |
| Face-swap (ArcFace `w600k_r50`, el de roop/FaceFusion), preset media | Identidad 0.70–0.82: **se conserva** (umbral 0.35) |
| Face-swap, preset fuerte | Identidad 0.51–0.66: **se conserva** |
| Face-swap con la nueva capa ArcFace, preset media (invisible) | ArcFace de roop/FaceFusion: **8/8 identidad rota** (media −0.00). ArcFace no visto (`glintr100`): **4/8** (media 0.32) |

La capa de rostro actual ataca a FaceNet y apenas se transfiere a ArcFace. La capa de difusión ataca a VAE abiertos que Gemini no usa.

## Decisiones

- **Solo perturbaciones invisibles** (≤ ±8/255, con presupuesto perceptual).
- Se publica lo que funcione y lo que no.
- Pruebas: **API de Gemini** automatizada (`engine/eval/assistants.py`) y **pruebas manuales en ChatGPT**, medidas con ArcFace.
- Solo se envían a servicios externos retratos de dominio público (`services/engine/samples/faces`).

## Estado del arte (2025–2026)

- **MIRAGE** ([arXiv 2606.26199](https://arxiv.org/abs/2606.26199)). Hace que el filtro de seguridad del editor rechace la foto. Con ±8/255: 89.6% en GPT-Image, 75% en Gemini, 77% en Grok. Sobrevive a JPEG 50, reescalado y capturas. Usa un ensamble de OpenCLIP (ViT-B-32, B-16, L-14 ×2, H-14), SigLIP-base, DINOv2-base y ShieldGemma-2, con 5000 pasos (~15 min/foto en una GPU A40).
  - Apunta a **contenido sexual**: lo descartamos, porque la moderación de las redes podría marcar la foto de la propia dueña.
  - Con **violencia** como objetivo cae al 2% en Gemini (±8/255). Copyright: sin medir.
- **M-Attack** ([arXiv 2503.10635](https://arxiv.org/abs/2503.10635), NeurIPS 2025; [código](https://github.com/VILA-Lab/M-Attack)). Ataque dirigido con un ensamble de CLIP y emparejamiento de recortes locales: más del 90% en GPT-4o/4.5 y transferencia a Gemini, pero en tareas de descripción, no de edición. Mejoras en M-Attack-V2 ([arXiv 2602.17645](https://arxiv.org/abs/2602.17645)).
- **VETO** ([arXiv 2607.27292](https://arxiv.org/abs/2607.27292)) y **Cross-Branch Conflict** ([arXiv 2607.16898](https://arxiv.org/abs/2607.16898)) atacan editores multimodales; solo con resultados en modelos abiertos.

## Enfoques

### A. Velo de identidad

Que el asistente "vea" otra cosa en lugar de la cara: lleva los embeddings de un ensamble (OpenCLIP, SigLIP, DINOv2) hacia un señuelo neutro, por ejemplo un busto de mármol de dominio público, usando recortes locales como M-Attack. Nunca hacia la cara de otra persona real. Sin riesgo de moderación para la dueña.

Éxito: Gemini devuelve una cara con identidad ArcFace < 0.35, o no reconoce la cara.

### B. Escudo de rechazo — descartado

No se desarrolla: consistiría en engañar a los sistemas de seguridad de servicios comerciales.

### C. Face-swap (ArcFace)

Atacar directamente a la familia ArcFace convirtiendo el ONNX a PyTorch, y medir la transferencia con otro ArcFace que no se ataque (`antelopev2`/`glintr100`).

**Pendiente de decidir:** los modelos de InsightFace tienen licencia de investigación no comercial. Opción: que cada persona los descargue de la fuente oficial, como hace FaceFusion.

## Cómputo

Los prototipos se hacen en CPU con ensambles pequeños (modelos base, 224 px). Las versiones completas necesitan GPU; para investigar sirven Kaggle o Colab gratis. Para el producto gratuito, el costo de GPU es un problema abierto.

## Advertencias

- Google y OpenAI cambian sus filtros y su preprocesado sin avisar: lo que funcione hay que volver a medirlo periódicamente.
- Un atacante con un modelo de difusión local puede limpiar la perturbación (lo reconoce el propio MIRAGE).


## Sello de "no uso" (hecho)

Como los asistentes cerrados no se frenan técnicamente con perturbaciones invisibles, cada foto protegida lleva además un sello verificable de que no se cede para IA (`engine/seal.py`):

- **Content Credentials (C2PA):** declaración firmada dentro de la foto con `c2pa.training-mining` en `notAllowed` para entrenamiento, entrenamiento generativo, inferencia y minería de datos. Estándar que leen Adobe, Google y otros. Se pierde si la red borra los metadatos.
- **Marca de agua invisible (TrustMark, Adobe, MIT):** identificador de 61 bits que **sobrevive a reescalado y JPEG 75** (verificado). Permite reconocer la foto como protegida aunque se borren los metadatos.
- **Verificación:** endpoint `POST /verify` y `python -m engine.seal <imagen>` ("¿esta imagen es mía?").
- **Certificados:** por ahora el par de desarrollo de C2PA (`python -m engine.setup_certs`); la firma es válida pero el firmante no es de confianza pública. Para producción, un certificado del programa de Content Credentials.

No impide el uso: deja **constancia verificable de que no hubo consentimiento**, con valor legal y para pedir retiradas.

## Plan de frontera: frenar también a los modelos grandes (intentado, cerrado como negativo)

> Esta sección documenta las hipótesis que se plantearon para esta frontera. **No se lograron**: los experimentos de [INVESTIGACION_TRANSFERENCIA.md](INVESTIGACION_TRANSFERENCIA.md) cerraron la línea (la perturbación invisible en CPU no transfiere a un modelo cerrado). Se conservan como registro, no como trabajo en curso.

No existe aún herramienta pública que, con perturbación invisible, frene la edición de modelos cerrados (Gemini, ChatGPT) de forma fiable. Sigue siendo un problema de investigación abierto (ver [PREGUNTAS_ABIERTAS.md](PREGUNTAS_ABIERTAS.md), B3). Lo intentamos construyendo y midiendo, sin prometer; lo que se midió se documenta abajo.

Estado del arte que usamos de base:
- **VETO** ([arXiv 2607.27292](https://arxiv.org/html/2607.27292v1)): ataca la atención de los editores DiT modernos; baja el éxito de edición de 66% a 1.3% en FLUX.2 (modelo abierto). Débil ante JPEG; no probado en cerrados.
- **M-Attack** ([arXiv 2503.10635](https://arxiv.org/abs/2503.10635)): ensamble de encoders de visión + recortes locales; >90% transferencia a GPT-4o/Gemini en descripción.
- **AEGIS** ([arXiv 2604.01635](https://arxiv.org/html/2604.01635)): inyecta la perturbación en la trayectoria de difusión; transferencia entre generadores abiertos.

Hipótesis a construir y medir (todo con presupuesto JND imperceptible):
1. **Velo de transferencia**: atacar un ensamble amplio de encoders de visión abiertos (OpenCLIP, SigLIP, DINOv2; añadir más) con recortes locales (M-Attack) hacia un señuelo neutro, para que el modelo grande "vea" otra cosa. Medir en Gemini (API o manual).
2. **Robustez EOT**: optimizar a través de JPEG/reescalado para no morir al subir a redes (lo que rompe a VETO).
3. **Entropía de atención** (idea de VETO) sobre un editor abierto como surrogate, y medir transferencia.
4. Combinar 1+2+3 y medir en Gemini/ChatGPT. Publicar funcione o no.

Cuello de botella honesto: cada medición en el modelo cerrado cuesta (API de pago de Gemini para imagen) o es manual. Sin medición real no se puede iterar.

### Resultado del velo de identidad, intento 1 (negativo)

Prototipo (`engine/research/assistant_shield.py`, ensamble OpenCLIP B-32/B-16 + SigLIP + DINOv2, ±8/255, 250 pasos, CPU). Medido con un CLIP ViT-L que el ataque NO vio, tras subir a redes (reescala + JPEG 75):

| Foto | "persona" antes | "persona" después |
|---|---|---|
| kim | 0.996 | 0.94 |
| jemison | 0.994 | 0.79 |

Con perturbación invisible y ensamble pequeño en CPU, la transferencia a un encoder no visto es débil: el modelo sigue viendo una persona. Coincide con la literatura (M-Attack necesita ensamble grande + eps mayor, y aun así es para descripción). Camino para el intento 2: ensamble más grande, más pasos, recortes locales más agresivos y, sobre todo, **GPU** (Kaggle/Colab) — en CPU no alcanza. Probar igualmente las fotos en Gemini manualmente, por si el proxy subestima el efecto.


## Auditoría anti-face-swap — qué significa el "8/8" (2026-10-17)

El "8/8" NO es un deepfake ejecutado: es la huella de identidad (ArcFace) de la foto protegida cayendo bajo el umbral de reconocimiento (0.35) frente a la original, en 8 retratos NASA de estudio, tras subir a redes. Es un proxy fuerte, no el face-swap real.

Medido en 4 reconocedores (identidad rota / 8):

| Reconocedor | ¿Atacado? | Rota | Media |
|---|---|---|---|
| w600k (buffalo_l, roop/FaceFusion) | sí | 8/8 | −0.00 |
| FaceNet-VGGFace2 | sí | 7/8 | 0.06 |
| glintr100 (antelopev2) | no | 4/8 | 0.32 |
| FaceNet-CASIA | no | 3/8 | 0.58 |

**Alcance real:** efectivo contra los reconocedores atacados (incluido el de las herramientas de face-swap comunes); parcial contra reconocedores no vistos (3-4/8). NO es universal. Solo retratos de estudio; falta variedad (selfies, ángulos, luz). No se ejecutó un face-swap real (pendiente: inswapper en CPU para validar el proxy).

**Fortalecimiento (siguiente):** atacar un ENSEMBLE de reconocedores (w600k + glintr100 + FaceNet-vgg + casia + más) y medir transferencia a uno dejado fuera. Misma lección que en transferencia: más diversidad = más cobertura. Pendiente de implementar y medir.
