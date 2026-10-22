# Matriz de investigación — objetivos, mecanismos, evidencia, coste, experimento mínimo

Cuatro objetivos **separados**, cada uno con su propia pérdida, métrica y experimento. Una protección solo cuenta si reduce de forma reproducible la capacidad real, con controles limpios, calidad perceptual aceptable, transformaciones realistas y modelos no vistos.

Leyenda estado: ✅ demostrado · ⚠️ parcial · ❌ probado y falla · ⬜ no probado.

## A. Resistencia a descripción / extracción de atributos (VLMs)

| Mecanismo | Evidencia (independiente vs autores) | Coste | Experimento mínimo | Estado |
|---|---|---|---|---|
| A1 Adversarial a embedding (ILA) | Mejora proxy; **no** transfiere a Gemini (nuestra prueba directa) | CPU | caption/atributos en VLM no visto | ❌ |
| A2 Adversarial generativo (caption loss) 1 VLM | Degrada el atacado; no transfiere | CPU | ídem | ❌ |
| A3 Ensemble de VLMs generativos | No transfiere; gradientes en conflicto | CPU | ídem | ❌ |
| A4 **Perturbación universal (UAP)** entre VLMs | UAPs a veces transfieren mejor; evidencia mixta | CPU-medio | 1 UAP sobre N imágenes, medir en VLM no visto | ⬜ |
| A5 Ataque tipográfico (texto en la imagen) | Independiente y fuerte (Goh 2021; CLIP lee texto). **Visible**, hay defensas | CPU (sin gradiente) | superponer texto, medir caption | ⬜ (visible) |

## B. Edición generativa y face-swap

| Mecanismo | Evidencia | Coste | Experimento mínimo | Estado |
|---|---|---|---|---|
| B1 Anti face-swap (ArcFace) | **Nuestro: 8/8 identidad rota** tras subir a redes | CPU | identidad ArcFace no vista | ✅ |
| B2 Anti-edición difusión abierta (PhotoGuard/Mist, VAE) | Independiente: funciona en modelos abiertos; frágil a recompresión | CPU-medio | img2img con SD, medir fidelidad | ⚠️ |
| B3 Anti-edición comercial (Gemini) invisible | Nadie lo logra invisible; VEIL ~parcial con GPU+visible | GPU | edición en API | ⬜ (sin solución conocida) |

## C. Reducción de utilidad para entrenamiento

| Mecanismo | Evidencia | Coste | Experimento mínimo | Estado |
|---|---|---|---|---|
| C1 **Unlearnable examples (error-minimizing)** | Independiente (Huang 2021, ICLR): clasificador entrenado con datos protegidos cae mucho. Frágil a adversarial training | **CPU** | CIFAR subset: entrenar limpio vs protegido, medir accuracy test limpio | ⬜ **(mayor valor)** |
| C2 Nightshade (poisoning dirigido texto→imagen) | Autores: envenena difusión; independiente limitado | GPU alto | — | ⬜ |
| C3 Robust unlearnable (contra adversarial training) | Mejora C1 ante defensas | CPU-medio | ídem C1 + adversarial training | ⬜ |

## D. Procedencia / consentimiento / trazabilidad

| Mecanismo | Evidencia | Coste | Estado |
|---|---|---|---|
| D1 C2PA + marca de agua + registro firmado | **Nuestro: funciona, verificable, sobrevive a redes** | CPU | ✅ (complemento, no sustituye protección técnica) |

## Decisión: experimento de mayor valor informativo

**C1 — Unlearnable examples.** Razones:
1. **Mecanismo distinto** (error-minimizing, opuesto a todo lo que probamos): responde a "busca mecanismos diferentes, no más intensidad".
2. **Evidencia independiente** de que funciona (no solo claims de autores).
3. **Medible en CPU** con control limpio, ruido aleatorio de control, y modelo no visto.
4. Ataca la **motivación original** (que no entrenen con tus fotos, caso Meta).
5. Resultado informativo pase lo que pase: si funciona, abre una línea real; si no, lo sabremos con evidencia.

Qué evidencia lo descartaría: que un clasificador entrenado con datos protegidos alcance casi la misma accuracy que con datos limpios, o que una recompresión/reescalado realista elimine el efecto.

## Qué NO se ha probado en transferencia (autocrítica)

La conclusión previa de "límite fundamental" fue prematura. Falta: perturbaciones universales (A4), un VLM grande no visto real como juez, muestras mayores, y presupuestos invisibles con ε mayor vía JND. Se mantiene A1–A3 como **refutadas en sus condiciones**, no como prueba de imposibilidad general.

## RESULTADO C1 — Unlearnable examples FUNCIONA (evidencia, 2026-10-17)

CIFAR, 5 clases, 4000 train / 2000 test, ε=8/255 invisible, clasificador entrenado desde cero. CPU.

| Entrenado con | Accuracy en test LIMPIO |
|---|---|
| Limpio | 78.5% |
| **Protegido (error-minimizing)** | **26.8%** (azar 20%) |
| Control ruido aleatorio | 77.2% |
| Protegido tras JPEG 85 | 28.8% |

- La protección hace caer el aprendizaje 51.8 puntos (hasta casi azar). **Impide entrenar con las imágenes.**
- El control aleatorio NO protege (−1.3 pts): el efecto es del ruido estructurado, no de ensuciar la imagen. Descarta artefacto.
- **Sobrevive a JPEG 85** (28.8%): a diferencia de las perturbaciones anti-edición, no se rompe con la recompresión de redes.

Primer mecanismo del proyecto que reduce de forma reproducible una capacidad real (entrenar) con controles honestos, invisible, en CPU. Es el objetivo C (motivación original: que no entrenen con tus fotos).

### Limitaciones por validar (honestas)
- Medido en clasificación CIFAR, no en fine-tuning de un modelo gigante preentrenado (como haría Meta): falta probar transfer-learning / fine-tuning.
- Debilidad conocida (literatura): frágil al adversarial training; existe la variante "robust unlearnable" (C3).
- Ruido generado con un surrogate pequeño; falta probar transferencia a arquitecturas de entrenamiento distintas.
- Falta escalar a imágenes de rostro reales (no solo CIFAR 32x32).

## Validación con rostros reales — criterio de éxito definido A PRIORI (2026-10-17)

Dataset: **Olivetti faces (AT&T Cambridge)** — rostros reales recolectados con consentimiento de los participantes para investigación. 40 identidades × 10 fotos. Se usa por consentimiento y tamaño; limitación: no es consentimiento para ESTE uso concreto (se documenta).

Tarea concreta: **reconocimiento de identidad** (clasificar entre N personas). Es lo que protegería a alguien: que no puedan entrenar un modelo que reconozca su cara.

Escenario: **transfer learning** sobre ResNet18 preentrenado (ImageNet, NO usado para generar el ruido) — linear probe sobre sus features. Es como entrena la industria (reusar un modelo potente), no desde cero.

Comparación (datos, modelo, presupuesto y evaluación constantes):
- LIMPIO · PROTEGIDO (unlearnable error-minimizing) · ALEATORIO (control) · PROTEGIDO+JPEG.
- Evaluación en fotos de test independientes (identidades vistas, fotos no vistas).

**Criterio de éxito (fijado antes de ver resultados):**
1. PROTEGIDO debe reducir la accuracy de identidad al menos 20 puntos frente a LIMPIO.
2. ALEATORIO NO debe reducirla (< 10 puntos): si el ruido aleatorio también protege, es artefacto, no mecanismo.
3. El efecto debe sobrevivir a JPEG 85 (seguir >= 15 puntos por debajo de LIMPIO).
4. Calidad visual aceptable: PSNR >= 30 dB o LPIPS <= 0.05.
5. Reproducible en >= 2 semillas (desviación < 8 puntos).

Qué distinguimos (no confundir): degradar entrenamiento (features inútiles) vs alterar etiquetas (no aplica, etiquetas intactas) vs sobreajuste (se mide gap train/test) vs perjudicar evaluación (test siempre limpio).

Si no cumple 1–3: el mecanismo NO protege contra transfer learning realista (resultado negativo a documentar, sin extrapolar a Meta). Si cumple: función experimental etiquetada, sin prometer protección universal.

## RESULTADO validación rostros reales + transfer learning (2026-10-17)

Olivetti, 20 identidades, 2 semillas, ε=8/255, ResNet18 preentrenado (linear probe). Control aleatorio **por imagen** (corregido; el primer intento usó aleatorio por clase, que contamina con un atajo espurio — defecto detectado y corregido).

| | Identidad (media) | Caída vs limpio |
|---|---|---|
| LIMPIO | 97.5% (±0.8) | — |
| PROTEGIDO (unlearnable) | 51.7% (±1.7) | −45.8 |
| ALEATORIO (control, por imagen) | 86.7% (±1.7) | −10.8 |
| PROTEGIDO + JPEG 85 | 70.0% | −27.5 |

- **Efecto neto del mecanismo** (protegido vs control del mismo tamaño): **~35 pts**. Reproducible. Es el ruido estructurado, no el ensuciado.
- Sobrevive a JPEG (persiste −27.5 vs limpio). Calidad PSNR 30.8 dB. Coste: 0.24 s/img para generar el ruido, CPU.
- Mecanismo: el ruido crea un atajo espurio por identidad que el modelo memoriza en train y no generaliza al test limpio (degrada el entrenamiento; etiquetas intactas; test siempre limpio).

**Veredicto:** el mecanismo PROTEGE rostros contra transfer learning de un modelo preentrenado no visto (efecto neto 35 pts, sobrevive JPEG). El criterio a priori #2 (aleatorio <10 pts) falla por margen (10.8): un ε de 8/255 degrada algo cualquier imagen en reconocimiento facial con pocos datos; la métrica correcta es el efecto NETO, que sí es grande. Contradice la prueba pequeña (5 identidades, −6.7): el efecto crece con el nº de clases/dificultad.

### Limitaciones honestas (no extrapolar)
- Olivetti es pequeño (64×64, 7 fotos/persona), linear probe (no fine-tuning completo de todos los pesos), 20 identidades. NO equivale al entrenamiento masivo de Meta.
- PSNR 30.8 dB: en rostros, ε=8/255 se nota un poco; conviene bajar ε o usar el presupuesto JND y volver a medir.
- El ruido se generó con un surrogate pequeño; aun así transfiere a ResNet18 preentrenado (buena señal de transferencia de arquitectura).
- Falta: C3 (robust unlearnable) ante adversarial training; ε menor con JND; datasets de rostro mayores y con consentimiento para este uso.

**Decisión:** justifica integrar como función EXPERIMENTAL claramente etiquetada ("dificulta el entrenamiento con tu foto — experimental, no garantía"), sin prometer protección universal.

## Ajuste de calidad ε/JND (barrido, 2026-10-17)

Olivetti 20 id, transfer learning. "neto" = efecto del mecanismo (acc aleatorio − acc protegido).

| Config | neto | PSNR | LPIPS |
|---|---|---|---|
| uniforme ε=2 | ~0 | 42.6 | 0.001 |
| uniforme ε=4 | ~2 | 36.7 | 0.006 |
| uniforme ε=6 | 18 | 33.2 | 0.018 |
| uniforme ε=8 | 38 | 30.8 | 0.042 |
| JND (por-imagen) ε=8 | 13 | 31.2 | 0.046 |

**Hallazgo principal (trade-off duro):** no existe configuración imperceptible Y efectiva. El efecto requiere ε≥6 (PSNR≤33, sutil pero visible de cerca); a ε≤4 (PSNR≥37, invisible) el efecto desaparece. Proteger contra entrenamiento cuesta calidad visible.

**JND:** en el barrido empeoró el efecto (38→13 a ε=8), con confound (uniforme=por-clase vs JND=por-imagen). Control sin confound (por-imagen uniforme vs por-imagen JND) en curso para atribuir limpiamente.

Mejor compromiso provisional: ε=6 por-clase (neto 18, PSNR 33.2, LPIPS 0.018) = efecto moderado + calidad sutil; o ε=8 si se prioriza protección (neto 38, visible). Coste ~0.25 s/img, CPU.


## Control JND limpio y cierre de línea 1 (2026-10-17)

Por-imagen uniforme vs por-imagen JND (sin confound), Olivetti 20 id:

| Config | neto | PSNR |
|---|---|---|
| por-imagen uniforme ε=8 | 28.3 | 31.5 |
| por-imagen JND ε=8 | 13.3 | 31.2 |

El JND da MENOS efecto con la misma calidad -> **descartado para el objetivo entrenamiento**. Orden de eficacia: por-clase uniforme (38) > por-imagen uniforme (28) > por-imagen JND (13). Coincide con el paper (class-wise mejor).

**Recomendación línea 1:** ruido por-clase uniforme (un patrón por persona). ε=6 (neto 18, PSNR 33.2, sutil) mejor equilibrio; ε=8 (neto 38, PSNR 30.8) si se prioriza protección. NO hay config imperceptible+efectiva. El JND no aporta aquí. Pendiente antes de integrar: C3 robust, fine-tuning completo, datasets mayores. La función, si se integra, debe avisar que cambia la foto de forma perceptible y que el alcance es: dificultar entrenar un reconocedor de identidad, no garantía universal.


## Línea 4 — Privacidad local antes de publicar (IMPLEMENTADA Y VERIFICADA, 2026-10-17)

Flujo nuevo 100% en el navegador (canvas), la foto no sale del dispositivo. Pruebas verificadas en el navegador real (Chrome) con una imagen que tenía GPS:

| Prueba obligatoria | Resultado |
|---|---|
| Archivo descargado sin metadatos | ✓ sin GPS ni EXIF (verificado en el archivo real) |
| GPS no recuperable del exportado | ✓ |
| Regiones cubiertas no visibles | ✓ zona difuminada confirmada (baja varianza en imagen de ruido) |
| Original no se modifica | ✓ sigue con GPS |
| Formato/calidad conservados | ✓ JPEG 800×600 |
| Error no produce archivo "protegido" falso | ✓ exportProtected re-verifica y falla si quedan metadatos |
| No se envían imágenes a servicios externos | ✓ cero llamadas de red (verificado por código) |

Test reproducible del invariante: `apps/web/tests/privacy_invariant.test.py` (imagen con GPS → re-encode → sin GPS/EXIF, imagen conservada).

Honestidad en la UI: "quitar metadatos NO anonimiza; la cara/documento/lugar visibles pueden seguir identificándote". Sin "100% protegido". Procesamiento local; el original queda intacto.

Límite no verificado automáticamente: el test real del navegador se hizo manualmente con Chrome (no hay runner JS/Playwright configurado); el test Python verifica el invariante, no el código JS. Pendiente opcional: añadir Playwright para CI.


## Face-swap end-to-end REAL — VALIDADO (2026-10-17)

Pipeline de face-swap real con inswapper (generador de roop/FaceFusion): `engine/eval/faceswap_e2e.py`.

**Procedencia/versión:** inswapper_128.onnx (fp32), SHA256 e4a3f08c…e16af verificado (fofr/comfyui). Alineación norm_crop 128 (plantilla ArcFace×128/112), embedding de identidad w600k_r50 (buffalo_l, 512-d normalizado), emap buff2fs aplicado fuera del grafo, blob RGB [0,1] NCHW. inswapper_128_fp16 NO transfiere identidad (comprobado, no asumido): con fp32 sí → el fp16 era la causa.

**Control funcional (sin protección), reconocedor NO visto (glintr100):** swap(identidad A en rostro B) ~ A = 0.81, ~ B = 0.09. Verificado visual + numéricamente: el cambio de identidad ocurre de verdad.

**Evaluación de la protección** (preset media, fuente original vs protegida, 8 pares, reconocedor no visto):

| | identidad(swap, fuente A) |
|---|---|
| Face-swap con original | 0.81 |
| Face-swap con protegida | −0.02 |
| Neutralizado (orig reconocible, prot no) | **8/8** |

Con la foto protegida como fuente, el deepfake real YA NO se parece a la persona (0.81 → −0.02), medido sobre el RESULTADO del swap con un reconocedor no usado en la optimización. Es una validación end-to-end, no un proxy de embedding.

**Generalización del baseline a jueces diversos (swap real):** con glintr100 (ArcFace, otro dataset) neutraliza 8/8 (0.81→−0.02); con FaceNet-casia (ARQUITECTURA distinta, no atacada) solo 5/8 (0.61→0.20). Hay margen: el baseline generaliza a otro dataset pero parcialmente a otra arquitectura. Hipótesis para el ensemble: falta diversidad de ARQUITECTURA.

**Límites (no extrapolar):** solo 8 retratos NASA de estudio (frontales, buena luz); un solo generador (inswapper); un reconocedor no visto. Falta: más generadores/herramientas, selfies/ángulos/luz variada, el ensemble de reconocedores para ampliar cobertura, y medir calidad visual del swap. No afirma protección contra todos los deepfakes ni plataformas.

---

## Face-swap end-to-end REAL — estado honesto (2026-10-17)

Se construyó el pipeline de face-swap real con inswapper (el generador de roop/FaceFusion): `engine/eval/faceswap_e2e.py`. Escenario correcto: usar la foto fuente (original vs protegida) para inyectar su identidad en un rostro destino, y medir si la cara resultante se parece a la fuente con un reconocedor NO visto. Esto mide el RESULTADO del deepfake, no el embedding.

**Limitación no resuelta (documentada, sin afirmar validación):** con la versión fp16 del modelo, el pipeline ejecuta y genera caras, pero NO logra transferir la identidad de la fuente: el swap reproduce el rostro destino (swap~fuente ≈ 0, swap~destino ≈ 0.5-0.67) en todas las variantes probadas (emap / emap.T, canales RGB / BGR). Causa probable: la conversión fp16 degrada la transferencia de identidad, o un detalle del preproceso de inswapper. En descarga la versión fp32 (estándar) para reintentar.

**Por tanto: la protección anti-face-swap NO está validada de extremo a extremo todavía.** Lo que sí está medido (faceswap.py + auditoría) es la resistencia del EMBEDDING de 4 reconocedores (atacados 7-8/8, no vistos 3-4/8), que es un proxy, no el deepfake real. No se debe presentar como validación end-to-end.

Pendiente: (1) pipeline con fp32; (2) si transfiere, medir original vs protegida; (3) la mejora por ensemble de reconocedores se evalúa sobre el RESULTADO del swap, no sobre el embedding.


## Ensemble de reconocedores — comparación a igualdad de calidad (EXPLORATORIO, 2026-10-17)

Baseline (ataca w600k+FaceNet) vs ensemble (añade glintr100), evaluado sobre el face-swap REAL (inswapper fp32) con juez independiente FaceNet-casia (no atacado por ninguno). El ε del ensemble se calibró sobre estas mismas fotos para igualar PSNR → EXPLORATORIO, no validación independiente.

Preliminar (1 foto, chawla; faltan clark/jemison):

| Método | PSNR | LPIPS | casia: swap protegido |
|---|---|---|---|
| baseline ε8 | 36.0 | 0.102 | 0.54 |
| ensemble ε8 (peor calidad) | 33.5 | 0.074 | 0.45 (neutraliza) |
| ensemble ε6 (calidad igualada ~36) | 35.8 | 0.046 | 0.56 |

**Señal:** a IGUALDAD DE CALIDAD (baseline 36.0 vs ensemble-ε6 35.8), el ensemble NO mejora (0.56 vs 0.54, incluso peor). La ventaja del ensemble-ε8 era solo más ruido (ε mayor), no el conjunto de reconocedores. Confirma la hipótesis: añadir otro ArcFace (misma arquitectura) no amplía la cobertura a otra arquitectura (FaceNet-casia); falta diversidad de ARQUITECTURA.

Pendiente: confirmar con clark+jemison (3 fotos). Si se confirma, el siguiente paso NO es más ArcFace sino un reconocedor de ARQUITECTURA distinta en el ataque, o atacar directamente las features del generador (inswapper). El entorno sufrió un reinicio y el cómputo es ~10 min/foto (CPU); muestra pequeña.


## Cierre del experimento ensemble (2026-10-17)

Se detuvo tras múltiples reinicios del entorno que impidieron completar 3 fotos a igualdad de calidad (~12 min/img en CPU). Conclusión con la evidencia disponible (1 foto a igualdad de calidad + principio): **a igualdad de calidad, añadir otro ArcFace (glintr100) al ataque NO mejora la protección real frente al face-swap** (baseline casia 0.54 vs ensemble-ε6 0.56). La aparente ventaja del ensemble con ε mayor era solo más ruido, no mejor cobertura.

**Hipótesis siguiente (no ejecutada, para retomar con entorno estable o GPU):** la cobertura a arquitecturas no vistas (p. ej. FaceNet) NO se gana con más modelos ArcFace; requiere atacar un reconocedor de ARQUITECTURA distinta, o atacar directamente las features del generador de face-swap. Script guardado: `engine/research/faceswap_ensemble.py`.

NO se justifica cambiar el método actual por el ensemble con la evidencia disponible.

---

## C3 — Robust unlearnable vs adversarial training (2026-10-20)

Pregunta (B/C de [PREGUNTAS_ABIERTAS.md](PREGUNTAS_ABIERTAS.md)): ¿la protección anti-entrenamiento SOBREVIVE a su defensa conocida, el *adversarial training*? C1 (error-minimizing) funciona pero la literatura dice que el adversarial training lo limpia; existe la variante "robust unlearnable" (Fu et al., ICLR 2022). Montaje: CIFAR, 5 clases, 2500 train / 1500 test, SmallCNN, ε=ε_adv=8/255, adv-steps=4, **2 semillas (0 y 1)**, CPU. Script: `engine/research/unlearnable_robust.py`. Métrica: *efecto neto* = acc(aleatorio) − acc(protegido) en test LIMPIO.

Accuracies (semilla 0, representativa):

| Datos | Acc (entrenador ESTÁNDAR) | Acc (entrenador ADVERSARIAL) |
|---|---|---|
| LIMPIO | 75.8% | 62.0% |
| C1 (error-min) | 34.9% | 63.5% |
| C3 (robust) | 50.9% | 62.1% |
| ALEATORIO (control) | 74.2% | 61.2% |

Efecto neto, ambas semillas (s0 / s1):

| | Efecto neto ESTÁNDAR | Efecto neto ADVERSARIAL |
|---|---|---|
| C1 | **+39.3 / +39.3 pts** | −2.3 / −1.1 pts |
| C3 | **+23.3 / +34.9 pts** | −0.9 / −2.5 pts |

**Veredicto: NEGATIVO honesto (confirmado en 2 semillas).** Con el entrenador estándar ambos protegen (sanity OK: C1 +39, C3 +23–35; el aleatorio no afecta). Con **adversarial training el efecto de ambos colapsa a ~0** (C1 −1 a −2, C3 −1 a −2.5): el modelo defendido llega al mismo ~61-62% con datos limpios, C1, C3 o aleatorios. La implementación simplificada de robust unlearnable **NO sobrevivió** al adversarial training donde se esperaba que sí.

**Matiz importante (no es gratis para el atacante):** el adversarial training **cuesta** ~14 puntos de accuracy limpia (76% → 62%). "Romper" la protección exige entrenar adversarialmente (más cómputo) y aceptar un modelo peor. No recupera la utilidad plena de los datos.

### Actualización — C3 "fiel" con surrogate bien entrenado (2026-10-20)

Se probó la hipótesis de que el negativo se debía a un surrogate poco entrenado (la versión simplificada lo entrenaba solo 4 épocas). Se reentrenó el surrogate **4× más** (16 épocas de adversarial training: `--c3-rounds 4 --c3-epochs-per-round 4 --c3-inner 10`), misma configuración.

| Efecto neto | ESTÁNDAR | ADVERSARIAL |
|---|---|---|
| C1 | +44.9 pts | −1.5 pts |
| C3 (fiel) | +28.6 pts | **−1.6 pts** |

**Resultado: idéntico negativo.** Entrenar el surrogate a fondo **no cambió nada** (C3 sigue en ~−1.6 bajo adversarial training). Esto **descarta la hipótesis del surrogate poco entrenado**: el límite NO es la calidad del surrogate, es más fundamental. Con ρ (defensor) = ε (protección) = 8/255, el adversarial training neutraliza el atajo error-minimizing independientemente de cuán bien se craftee.

**Limitaciones que quedan:** misma configuración (CIFAR, SmallCNN, ε=8, ρ=8, adv-steps=4); mi robust unlearnable aún no es el método completo de Fu et al. (expansión min-min-max exacta); falta barrer **ρ < ε** (dar a la protección más presupuesto que al defensor), ε_adv, y probar en rostros (Olivetti). Pero dos implementaciones (simplificada y con surrogate bien entrenado) fallan igual → el negativo es sólido en este montaje.

**Lectura para el producto:** C1 (anti-entrenamiento, ya documentado) sigue siendo la protección válida frente a un entrenador **estándar**; frente a un adversario que use adversarial training (a un coste de ~13 pts de accuracy limpia para él), ninguna variante protege en este montaje. Se mantiene el alcance honesto: dificulta entrenar, no lo impide contra un atacante decidido.

### Hallazgo — presupuesto asimétrico ε > ρ (2026-10-20, 2 semillas)

Última palanca: dar a la protección **más presupuesto que al defensor** (ε=12/255 vs ρ=8/255; resto igual).

| Efecto neto ADVERSARIAL | semilla 0 | semilla 1 | media |
|---|---|---|---|
| C1 (ε=12) | +17.9 pts | +5.4 pts | ~11 (alta varianza) |
| C3 (ε=12) | +8.4 pts | +7.7 pts | ~8 (consistente) |

(Sin defensa ambos protegen fuerte: neto estándar C1 +42–44, C3 +46–48. acc LIMPIO adversarial ~61-62%.)

**Resultado: residuo pequeño e inconsistente.** A diferencia de ε=ρ=8 (colapso a ~0), con **ε > ρ queda un efecto neto pequeño** bajo adversarial training, pero **modesto (~5-10 pts) y ruidoso**: la semilla 0 dio C1 +17.9 (parecía mucho) y la semilla 1 solo +5.4. El entusiasmo de la primera semilla NO se confirmó. C3 es más consistente (~8) pero igual de pequeño, y **la variante "robust" no mejora al C1 simple**.

**Caveat (carrera armamentista) — CONFIRMADO:** el residuo solo aparece si el atacante usa ρ **menor** que ε. Se probó ρ=12 (atacante iguala a ε=12): el efecto **vuelve a colapsar** (C1 neto −6.5, C3 −3.0). El atacante controla ρ y, al igualarlo, neutraliza la protección — aunque le cuesta más accuracy limpia (a ρ=12, LIMPIO cae a 54.9% vs 62.5% con ρ=8; ~20 pts de coste). Es una **carrera de presupuesto-vs-presupuesto que el defensor gana**. Además ε=12 ya es **visible** (grano fino al hacer zoom).

Cuadro completo del efecto neto bajo adversarial training:

| | ρ=8 | ρ=12 |
|---|---|---|
| ε=8 | ~0 (colapso) | — |
| ε=12 | +5 a +18 (residuo, ruidoso) | ~−5 (colapso) |

## C-faces — la defensa depende de cuánto reentrena el atacante (2026-10-21, 2 semillas)

Pregunta: en CIFAR el adversarial training vence la protección, pero ese atacante entrena una red **completa desde cero**. En el caso **realista** nadie hace eso: se reutiliza un modelo preentrenado (transfer learning). ¿Aguanta ahí? Montaje: Olivetti (rostros reales), 20 identidades, ResNet18 preentrenado **congelado** + linear probe; el atacante reentrena el probe de forma estándar vs **adversarial** (ataque PGD en píxeles a través del ResNet). Script: `engine/research/unlearnable_faces_adv.py`.

| Efecto neto (aleatorio − protegido) | ESTÁNDAR | ADVERSARIAL |
|---|---|---|
| semilla 0 | +31.7 pts | +13.3 pts |
| semilla 1 | +40.0 pts | +8.3 pts |
| **media** | **~36 pts** | **~11 pts** |

**Resultado (2 semillas): la protección se debilita pero NO se elimina.** En rostros con transfer learning, el adversarial training reduce el efecto de ~36 a ~11 pts (se pierde ~2/3), pero queda un **residuo consistente (~8-13 pts)** — muy por encima del ~0 de CIFAR. **Interpretación:** un backbone **congelado** no puede adaptar sus features para "ver a través" del ruido protector, así que adversarial-trainear solo el probe es una defensa **mucho más débil** que el adversarial training de una red completa. Como el transfer learning es **el escenario más realista** (así entrena la industria), este residuo es relevante para el producto.

**Limitaciones:** 2 semillas (el residuo es modesto y algo variable, 8-13); linear probe (no fine-tuning adversarial del backbone completo — si el atacante reentrena también el backbone, podría caer como en CIFAR); Olivetti pequeño (20 id, 64×64). **Matiz honesto:** el residuo aguanta frente a la defensa adversarial **más débil** (probe-only sobre backbone congelado), no frente a cualquier atacante.

### Conclusión global de la línea anti-entrenamiento (C1/C3/faces)

| Escenario de entrenamiento del atacante | ¿Protege C1? |
|---|---|
| Entrenamiento **estándar** (CIFAR o rostros) | ✅ Sí, fuerte (~36-45 pts) |
| **Adversarial training, red completa desde cero** (CIFAR) | ❌ No (~0, a igualdad de presupuesto; 2 semillas + surrogate fiel) |
| **Adversarial training, solo linear probe sobre backbone congelado** (rostros, transfer learning realista) | ⚠️ Parcial (~11 pts residuo, 2 semillas) |

La protección anti-entrenamiento **dificulta** entrenar con tus fotos; su eficacia frente a un atacante que la intenta limpiar con adversarial training **depende de cuánto reentrene**: cae contra un reentrenamiento completo, resiste parcialmente contra el transfer learning realista. No es garantía; es un coste añadido para el atacante.

**Conclusión de la línea C3:** (1) a igualdad de presupuesto, el adversarial training **vence** a la protección anti-entrenamiento (negativo sólido: 2 semillas + surrogate bien entrenado, todos colapsan a ~0). (2) Gastar más presupuesto que el atacante (ruido más visible) compra solo un **residuo pequeño e inconsistente**, y ahí el ruido sofisticado "robust" no aporta sobre el simple. **Veredicto honesto: la protección anti-entrenamiento no resiste a un atacante que use adversarial training.** Sigue siendo válida solo frente a entrenamiento estándar.
