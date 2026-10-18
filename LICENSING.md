# Licencias y avisos de terceros

## El código de Image Privacy Toolkit

El código de este repositorio está bajo la **[Licencia MIT](LICENSE)** · Copyright (c) 2026 Yuthramys Ibarra.

La MIT permite usar, copiar, modificar, combinar, publicar, distribuir, sublicenciar y **vender** copias del software, incluso con fines comerciales y en productos de código cerrado, siempre que se conserven el aviso de copyright y el de la licencia. No hay tarifas ni suscripción para usar el código bajo esos términos.

La gratuidad del **código** es independiente de los costes de un posible **alojamiento web**: ejecutar una demo pública tiene un coste de operación que no cambia la licencia del código.

## Imágenes de muestra incluidas (no son parte del código)

Las imágenes de `services/engine/samples/` se incluyen solo para pruebas y no se relicencian bajo MIT; conservan su licencia de origen, documentada junto a ellas:

| Carpeta | Contenido | Licencia / fuente |
|---|---|---|
| `samples/` | `astronaut.png` (Eileen Collins, NASA), `chelsea.png`, `coffee.png` | Dominio público / CC0 (muestras de scikit-image) |
| `samples/faces/` | Retratos oficiales de astronautas de la NASA | Dominio público (Wikimedia Commons; ver `samples/faces/README.md`) |
| `samples/decoys/` | Bustos de mármol (The Met Open Access) | CC0 (ver `samples/decoys/README.md`) |

## Modelos de terceros (los descarga el usuario; no se distribuyen en el repo)

El motor de perturbación puede usar modelos preentrenados que **no forman parte de este repositorio** y que cada quien descarga por su cuenta. Cada modelo conserva su propia licencia:

| Modelo | Licencia | Nota |
|---|---|---|
| FaceNet InceptionResnetV1 + MTCNN (`facenet-pytorch`) | MIT | — |
| `stabilityai/sd-vae-ft-mse` | MIT | — |
| VAE de `ostris/Flex.1-alpha` | Apache-2.0 | — |
| `madebyollin/taesd`, `madebyollin/taef1`, `madebyollin/sdxl-vae-fp16-fix` | MIT | — |
| LPIPS (AlexNet) | BSD-2 | — |
| **InsightFace ArcFace** (`buffalo_l`, `antelopev2` / `glintr100`) | **Solo investigación no comercial** | Lo descarga el usuario (`engine/models.py`). |
| **inswapper_128** (InsightFace) | **Solo investigación no comercial** | Se usa únicamente para la evaluación de face-swap. |

**Importante:** la licencia MIT cubre el código de Image Privacy Toolkit, no estos modelos. Las funciones que dependen de **InsightFace ArcFace** (la capa de rostro con ArcFace y la evaluación de face-swap) están sujetas a la licencia **no comercial** de esos modelos. Si alguien quiere usar esas funciones concretas con fines comerciales, debe revisar y respetar los términos de InsightFace, o sustituirlos por alternativas permisivas (por ejemplo, usar solo FaceNet, MIT). El código no incorpora ni relicencia código de terceros.

## Dependencias

Las dependencias de Python (`services/engine/requirements.txt`) y de Node (`apps/web/package.json`) conservan cada una su propia licencia (en su mayoría MIT, BSD o Apache-2.0). Instalarlas no cambia la licencia de Image Privacy Toolkit.
