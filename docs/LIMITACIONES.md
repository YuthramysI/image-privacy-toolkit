# Qué protege Image Privacy Toolkit y qué no

Este documento existe para que nadie confíe en Image Privacy Toolkit más de lo que debe.

## Lo que sí hace

- **Reconocimiento facial.** Es la capa más sólida. Contra el modelo atacado, la identidad deja de coincidir incluso después de reescalar y recomprimir la foto. Contra un reconocedor distinto que el ataque nunca vio, el parecido baja a la zona del umbral de coincidencia: dificulta el reconocimiento, pero no lo impide siempre.
- **Edición y entrenamiento con modelos de difusión abiertos** (Stable Diffusion, FLUX). La perturbación degrada lo que el modelo "ve" de la foto, también en un VAE que no se atacó (SDXL). Con los presets invisibles el efecto es **modesto**: la IA sigue viendo la foto, solo peor. El preset Fuerte duplica aproximadamente el efecto a cambio de una textura visible al hacer zoom.
- **Reserva legal.** Los metadatos declaran que la imagen no puede usarse para minería de datos ni entrenamiento (IPTC PLUS). Sirve como prueba de la reserva de derechos.

## Lo que no puede prometer

1. **No frena a los asistentes cerrados.** Gemini, ChatGPT, Meta AI y similares usan modelos privados con otra arquitectura y su propio preprocesado. En una prueba real, Gemini editó una foto protegida (le añadió lentes de sol conservando el rostro) sin ningún problema. Hoy ninguna herramienta de este tipo los frena de forma fiable.
2. **No hay garantía total.** Hay trabajos publicados que reducen o eliminan perturbaciones como esta con técnicas simples: purificación con un modelo de difusión, superresolución o filtros de ruido. Un atacante decidido puede limpiar la imagen.
3. **Transferencia limitada.** La perturbación se optimiza contra modelos concretos (FaceNet, VAE de SD y FLUX). Los modelos privados de las grandes plataformas son distintos y el efecto sobre ellos es menor y desconocido.
4. **Transformaciones fuertes.** Resiste el reescalado y la recompresión JPEG típicos de las redes sociales, pero se debilita con recortes agresivos, filtros, capturas de pantalla a baja resolución o fotos de la pantalla.
5. **Metadatos.** Muchas redes sociales borran los metadatos al subir la foto, así que la reserva legal solo viaja si se comparte el archivo tal cual.
6. **Lo que ya está publicado.** No protege copias anteriores de la foto que ya circulan sin perturbar.
7. **Modelos futuros.** Un modelo entrenado después, o entrenado para ignorar este tipo de ruido, puede no verse afectado.

## Cómo se mide

`services/engine/engine/eval/run.py` simula dos escenarios: una subida a una red social (1080 px y JPEG 75) y un pipeline de entrenamiento (512 px y JPEG 85). Después mide:

- **Visibilidad:** PSNR, SSIM y LPIPS entre la foto original y la protegida.
- **Rostro:** similitud coseno de la identidad entre la original y la protegida, con el modelo atacado y con uno no visto. Un valor por debajo de ~0.5 suele considerarse "otra persona".
- **Difusión:** PSNR de la reconstrucción del VAE (lo que "ve" el modelo) frente a la foto limpia, con los VAE completos de SD, FLUX y SDXL. Cuantos más dB cae, más basura ve el modelo.

Las cifras actuales están en el [README](../README.md#métricas-medidas-no-prometidas). Si cambias el algoritmo, vuelve a medir y actualiza la tabla.

## Pendiente de medir

- Resultado real de img2img y de un fine-tuning LoRA con fotos protegidas frente a fotos limpias. Es la prueba definitiva; requiere GPU.
- Resistencia a purificación (por ejemplo, superresolución o un paso de difusión limpio).
- Más imágenes de prueba, con diversidad de rostros, tonos de piel e iluminación.
