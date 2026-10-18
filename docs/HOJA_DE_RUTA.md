# Hoja de ruta

> Las líneas de investigación sin resolver, con su criterio de éxito/fracaso y su coste de cómputo, están en **[PREGUNTAS_ABIERTAS.md](PREGUNTAS_ABIERTAS.md)**. Cómo contribuir: **[CONTRIBUTING.md](../CONTRIBUTING.md)**.

## Hecho

- Motor de protección por capas (rostro + difusión + EOT + presupuesto perceptual).
- Reserva legal en metadatos IPTC/XMP.
- Benchmark con modelos no atacados.
- API con cola, progreso en vivo y borrado automático.
- Interfaz web con comparador y vista de la diferencia.

## Siguiente: medir mejor

- Prueba real de img2img y de fine-tuning LoRA con fotos protegidas (necesita GPU).
- Prueba contra purificación (superresolución, difusión limpia).
- Ampliar las imágenes de prueba con rostros diversos y licencia libre.

## Después: rastreo y alertas

La idea es avisar cuando una copia o captura de una foto protegida aparezca en la web.

1. **Huella perceptual.** Al proteger una foto se calcula su PDQ (algoritmo de Meta, BSD, resistente a capturas) y su pHash. Se guarda solo la huella, nunca la foto.
2. **Marca de agua invisible.** Se incrusta con TrustMark (Adobe, MIT), que resiste capturas de pantalla, en este orden: marca de agua, luego perturbación, y luego se comprueba que la marca se siga leyendo. Watermark Anything se descarta porque su licencia es no comercial.
3. **"¿Esta imagen es mía?"** Un endpoint lee la marca de agua o compara la huella con la base de datos (SQLite o Postgres).
4. **Búsqueda (fuera de alcance por ahora).** Se exploró un motor de búsqueda facial propio y se descartó (2026-10-18): sin indexar la fuente no es funcional como un "PimEyes", y un buscador facial de terceros es terreno legal delicado (biométrico, GDPR, Clearview AI). Si algún día se retoma, lo viable sería un adaptador a una API de pago que ya haya indexado la web (TinEye para imágenes; FaceCheck/Lenso para rostros), no un rastreador biométrico propio.
5. **Alertas.** Por correo, con el plan gratuito de Resend o con SMTP propio.

Requiere cuentas de usuario para asociar huellas y alertas, así que hay que decidir cómo guardar el mínimo de datos personales.

## Otras ideas

- Firma C2PA con una aserción de "no entrenar" (requiere un certificado de firma).
- Versión ligera de la capa de rostro en el navegador (ONNX Runtime Web), para que la foto no salga del dispositivo.
- Demo pública gratuita: web en Vercel o Netlify y motor en un Space de Hugging Face (CPU gratuita).
