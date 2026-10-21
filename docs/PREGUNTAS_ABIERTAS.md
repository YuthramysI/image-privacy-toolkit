# Preguntas abiertas de investigación

Image Privacy Toolkit es, en su parte de perturbación, un **proyecto de investigación abierta**. No afirmamos haber resuelto la protección de fotos frente a la IA: afirmamos haber medido, con controles honestos, qué funciona hoy y qué no. Este documento reúne las **preguntas que siguen abiertas** para que cualquiera pueda retomarlas, refutarlas o avanzarlas.

Cada pregunta indica: qué sabemos ya (con enlace a la evidencia), qué falta, el coste estimado de cómputo y un **criterio de éxito o fracaso fijado de antemano**. Si contribuyes con un experimento, el valor está en el método y en publicar el resultado —**incluido el negativo**—, no en "lograr que proteja".

Estado: ✅ demostrado · ⚠️ parcial · ❌ probado y falla · ⬜ no probado. Evidencia completa en [MATRIZ_INVESTIGACION.md](MATRIZ_INVESTIGACION.md).

---

## Reglas de una contribución de investigación

Para que un resultado cuente, un experimento debe tener:

1. **Control limpio** (imagen sin tocar) y **control de ruido aleatorio** del mismo tamaño (ε): si el ruido aleatorio protege igual, el efecto es artefacto, no mecanismo. Se mide el **efecto neto** (protegido vs control aleatorio), no solo protegido vs limpio.
2. **Modelo no visto** como juez: un modelo que **no** se usó para generar la perturbación. Atacar y evaluar con el mismo modelo no demuestra nada transferible.
3. **Transformación realista** antes de evaluar: reescalado + JPEG (simula subir a una red social). Una protección que muere al recomprimir no sirve.
4. **Criterio de éxito/fracaso escrito ANTES** de ver los resultados, para no mover la portería.
5. **Calidad perceptual medida** (PSNR y LPIPS): una protección visible es un resultado distinto a una invisible; hay que decir cuál es.
6. **Reproducible** en ≥2 semillas y con el comando exacto para repetirlo.

---

## A. Que un modelo no pueda describir / etiquetar la foto (VLMs y buscadores)

### A4 · Perturbación universal (UAP) que transfiera entre VLMs ⬜ (mayor valor de esta familia)

- **Qué sabemos:** atacar el *embedding final* de un codificador sobreajusta a cada modelo y **no** transfiere a uno cerrado como Gemini (❌, [INVESTIGACION_TRANSFERENCIA.md](INVESTIGACION_TRANSFERENCIA.md)). Atacar *activaciones intermedias* (ILA) mejora la proporción que transfiere ~3–6× pero sigue siendo débil en absoluto (⚠️).
- **Hipótesis abierta:** una **única** perturbación optimizada sobre N imágenes a la vez (universal), en vez de una por imagen, podría capturar rasgos compartidos entre arquitecturas y transferir mejor a un juez no visto. La literatura de UAPs lo sugiere, con evidencia mixta.
- **Falta:** implementar el bucle UAP (una δ para un lote), con ILA sobre la capa intermedia, y medirlo en un VLM grande no visto real.
- **Coste:** CPU-medio (horas).
- **Éxito:** la δ universal degrada el caption/etiqueta de un VLM **no visto** de forma medible y reproducible tras subir a redes, con efecto neto > control aleatorio. **Fracaso:** no mejora sobre la perturbación por imagen → se documenta y se cierra la línea de UAP invisible.

### A5 · Ataque tipográfico (texto superpuesto) ⬜ (visible)

- **Qué sabemos:** es independiente y fuerte (Goh et al. 2021: CLIP "lee" el texto de la imagen y se deja guiar por él). La contrapartida es que es **visible** y hay defensas (OCR, filtros).
- **Falta:** medir cuánto degrada el caption de un VLM y cuánto resiste a defensas simples.
- **Coste:** CPU (sin gradiente).
- **Éxito:** reduce la calidad del caption de forma clara. Es un mecanismo **visible** por diseño: su interés es como opción consciente ("acepto una marca visible a cambio de más efecto"), no como protección invisible.

---

## B. Que no puedan editar la foto ni hacer deepfakes

### B-faceswap · Atacar otra arquitectura o el generador directamente ⬜

- **Qué sabemos:** la capa anti-face-swap **funciona** de extremo a extremo contra `inswapper` con un reconocedor no visto del mismo tipo (ArcFace): identidad rota 8/8 tras subir a redes (✅, [MATRIZ_INVESTIGACION.md](MATRIZ_INVESTIGACION.md)). Pero generaliza solo **parcialmente** a una arquitectura distinta (FaceNet: 5/8). Añadir otro reconocedor ArcFace al ataque **no** amplía la cobertura (medido a igualdad de calidad).
- **Hipótesis abierta:** la cobertura a arquitecturas no vistas no se gana con más modelos del mismo tipo, sino (a) atacando un reconocedor de **arquitectura distinta** en la optimización, o (b) atacando directamente las **features internas del generador** de face-swap.
- **Falta:** implementar cualquiera de las dos vías y medir sobre el face-swap real con un juez de tercera arquitectura.
- **Coste:** CPU alto (~10–12 min/imagen) o GPU. Script de partida: `engine/research/faceswap_ensemble.py`.
- **Éxito:** sube la neutralización en una arquitectura no vista (p. ej. FaceNet) de 5/8 a ≥7/8 **a igualdad de calidad** (mismo PSNR).

### B3 · Edición por un modelo comercial (Gemini / ChatGPT) invisible ⬜ (sin solución conocida)

- **Qué sabemos:** **nadie** ha logrado una protección invisible que impida la edición con un modelo comercial cerrado. En una prueba directa nuestra, Gemini editó una foto protegida sin problema. Trabajos como VEIL logran algo **parcial** pero con GPU y perturbación **visible**.
- **Honestidad:** esta es la pregunta más difícil y la que más humo atrae. Mientras no haya evidencia reproducible con juez no visto, el proyecto **no** anunciará protección contra edición comercial.
- **Éxito:** cualquier resultado reproducible aquí sería un hallazgo de primer nivel; trátalo con escepticismo extra (controles, modelo realmente no visto, y que sobreviva a recompresión).

---

## C. Que no puedan entrenar con tus fotos (el motivo original: caso Meta)

### C1 · Unlearnable examples ✅ (demostrado en condiciones controladas)

- **Qué sabemos:** el ruido *error-minimizing* por clase hace caer el entrenamiento de un reconocedor de identidad ~35 puntos de efecto neto (vs control aleatorio), sobre rostros reales (Olivetti) y transfer learning de un ResNet18 preentrenado no visto; **sobrevive a JPEG 85** (✅). El límite duro: **no existe configuración imperceptible Y efectiva** —el efecto necesita ε≥6 (sutil pero visible de cerca).
- **Esto es lo más sólido del eje "entrenamiento"** y la base de las dos preguntas siguientes.

### C3 · Robust unlearnable (contra adversarial training) ⚠️ (negativo preliminar, 2026-10-20)

- **Qué sabemos:** C1 tiene una debilidad conocida: si quien entrena usa **adversarial training**, recupera la utilidad de las fotos. Se implementó "robust unlearnable" (Fu et al., ICLR 2022) en `engine/research/unlearnable_robust.py` y se probó en CIFAR, 5 clases. **Resultado negativo robusto** (2 semillas + versión con surrogate bien entrenado): sin defensa C1 (+39–45 pts) y C3 (+23–35 pts) protegen; con adversarial training **ambos colapsan a ~0**. Entrenar el surrogate 4× más **no ayudó** → descarta la hipótesis del surrogate poco entrenado; el límite es más fundamental (con ρ_defensor = ε_protección, el adversarial training neutraliza el atajo). Matiz: la defensa cuesta al atacante ~13 pts de accuracy limpia. Detalle en [MATRIZ_INVESTIGACION.md](MATRIZ_INVESTIGACION.md).
- **Probado — presupuesto asimétrico ε>ρ (2026-10-20, 2 semillas):** con ε=12/255 vs ρ=8/255 queda solo un **residuo pequeño e inconsistente** bajo adversarial training (C1 neto +17.9 en s0 pero +5.4 en s1; C3 ~+8 estable). El salto grande de la 1ª semilla **no se confirmó**. La variante "robust" C3 no mejora al C1 simple. Detalle en [MATRIZ_INVESTIGACION.md](MATRIZ_INVESTIGACION.md).
- **Falta (opcional, para cerrar el cuadro):** ρ=12 (atacante iguala presupuesto → confirmar colapso); el montaje de rostros (Olivetti); la expansión min-min-max exacta de Fu et al.
- **Coste:** CPU-medio (~50 min a 3 hilos por corrida).
- **Estado (conclusión):** a igualdad de presupuesto el adversarial training **vence** la protección anti-entrenamiento (negativo sólido); con más presupuesto que el atacante queda un residuo pequeño y ruidoso. **No es una garantía; vale solo frente a entrenamiento estándar.**

### C-escala · Escalar unlearnable a datos de rostro mayores y fine-tuning completo ⬜

- **Qué sabemos:** C1 se midió en Olivetti (pequeño, 64×64, linear probe), **no** en fine-tuning completo de un modelo grande como haría una empresa.
- **Falta:** un dataset de rostros mayor **con consentimiento para este uso**, y fine-tuning de todos los pesos (no solo linear probe).
- **Coste:** GPU recomendable.
- **Éxito:** el efecto neto persiste al escalar. Esto acercaría la evidencia al escenario real (entrenamiento masivo), sin llegar a demostrarlo para una empresa concreta.

### Presupuesto perceptual · Bajar ε manteniendo efecto ⬜

- **Qué sabemos:** el JND probado **empeoró** el efecto (descartado). El trade-off calidad/efecto sigue siendo duro.
- **Falta:** máscaras perceptuales más finas (p. ej. basadas en textura/saliencia) que concentren el ruido donde no se ve, buscando efecto a PSNR ≥ 35.
- **Éxito:** efecto neto ≥20 pts a PSNR ≥ 35 dB (hoy ese efecto exige PSNR ~31).

---

## D. Procedencia y trazabilidad ✅ (complemento, no sustituye)

- C2PA + marca de agua + registro firmado **funciona y sobrevive a redes** (✅). No impide el uso técnico; deja constancia verificable del no-consentimiento. Línea madura; mejoras bienvenidas (más formatos, robustez de la marca).

---

## Infraestructura y verificación (contribuciones de ingeniería)

- ⬜ **CI con Playwright** para el flujo de privacidad local (hoy el test de navegador es manual; el invariante Python sí está automatizado).
- ⬜ **Más imágenes de prueba** con rostros diversos y **licencia libre / consentimiento explícito** (hoy el muestreo es pequeño y de estudio).
- ⬜ **Benchmark reproducible en un contenedor** con los modelos cacheados, para que cualquiera repita las métricas sin fricción.
- ⬜ **Purificación como adversario:** medir cuánto elimina cada protección un paso de superresolución o de difusión limpia (ataque de quien quiere saltarse la protección). Es la prueba honesta de robustez.

---

## Cómo proponer una pregunta nueva

Abre una *issue* con la etiqueta `investigación` que incluya: el objetivo (A/B/C/D), la hipótesis, el modelo no visto que usarías como juez, el control, y el criterio de éxito/fracaso **antes** de correr nada. Ver [CONTRIBUTING.md](../CONTRIBUTING.md).
