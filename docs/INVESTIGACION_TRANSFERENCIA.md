# Investigación: transferencia de perturbaciones a modelos no vistos

Objetivo: que una perturbación invisible optimizada contra pocos codificadores de visión en CPU degrade lo que extrae un codificador **no visto** (proxy de un modelo cerrado grande). Todo medido **después** de subir la imagen a redes (reescalado + JPEG).

Separación de objetivos (no se mezclan):
- **Representación / descripción / etiqueta** (lo que aquí se investiga): atacar los codificadores de visión que comparten los VLM.
- **Edición generativa** (poner lentes, deepfake): distinto; no se resuelve con esto.
- **Entrenamiento / fine-tuning**: distinto; evaluación aparte.

## Diagnóstico (por qué fallaba, con evidencia)

Experimento `exp_aggr` sobre un retrato, midiendo similitud a la etiqueta señuelo en los modelos atacados y en el juez no visto, tras subir a redes:

| Config | Atacados (señuelo) | Juez no visto (señuelo) |
|---|---|---|
| Limpio | 0.045 | 0.018 |
| Invisible ε6 + LPIPS 3.0 + EOT fuerte | 0.074 | 0.018 (nada) |
| ε12 sin LPIPS | 0.111 | 0.052 |

Conclusiones:
1. **No era un bug**: con ε suficiente el ataque sí mueve los modelos atacados.
2. **Sobre-restricción**: la config "invisible" casi no movía ni los atacados (ε bajo + LPIPS fuerte + recortes agresivos diluían la señal).
3. **Sobreajuste + transferencia débil**: con el embedding final, los atacados se mueven mucho más que el juez.

## Hipótesis H-ILA y resultado

**Hipótesis**: atacar el *embedding final* de CLIP sobreajusta a cada modelo; atacar las *activaciones intermedias* (rasgos genéricos compartidos entre arquitecturas) transfiere mejor. Base: Intermediate Level Attack (Huang et al. 2019), aquí aplicado a CLIP para protección.

Laboratorio `engine/research/transfer_lab.py`. Métrica de transferencia: distancia coseno del embedding del juez no visto entre imagen limpia y protegida, tras subir a redes (mayor = más transferencia). ε=8/255, 120 pasos, 4 modelos atacados + 1 juez.

| Foto | Método | Transferencia (juez) | Sobreajuste (atacados) |
|---|---|---|---|
| kim | baseline (final) | 0.022 | 0.432 |
| kim | **ILA (intermedio)** | 0.023 | 0.157 |
| jemison | baseline (final) | 0.048 | 0.741 |
| jemison | **ILA (intermedio)** | **0.121** | 0.294 |

- ILA mejora la **proporción que transfiere** (juez/atacados) de forma consistente: ~3x en kim, ~6x en jemison.
- En transferencia absoluta, ILA gana hasta 2.5x (jemison).
- Observación: las imágenes con más textura transfieren mucho mejor que las de superficies lisas.

### Validación con 6 retratos

Transferencia al juez no visto (distancia coseno; mayor = mejor):

| Foto | baseline | ILA |
|---|---|---|
| kim | 0.022 | 0.023 |
| jemison | 0.048 | **0.121** |
| chawla | 0.032 | 0.026 |
| clark | 0.040 | **0.096** |
| melroy | 0.038 | **0.059** |
| rubio | 0.015 | **0.019** |
| **Media** | **0.033** | **0.057 (+76%)** |

ILA gana en **5 de 6** retratos y mejora la transferencia media **+76%**, con visibilidad (LPIPS) casi idéntica. En las 6, ILA distorsiona mucho menos los modelos atacados (0.12–0.29 vs 0.33–0.74), es decir, **sobreajusta menos y transfiere más**: eficiencia de transferencia ~4x. Resultado robusto. Conclusión: atacar capas intermedias es mejor que atacar el embedding final para transferir a un modelo no visto. Se adopta ILA como método por defecto del módulo 2.

### ¿Transfiere entre arquitecturas distintas? (sí)

Experimento `exp_crossarch`: perturbación ILA optimizada solo en ViT-B, medida en dos jueces no vistos: uno ViT-B (misma familia) y uno **ConvNeXt** (convolucional, arquitectura distinta; proxy de un modelo cerrado de arquitectura desconocida).

| Foto | Juez ViT (misma arq.) | Juez ConvNeXt (otra arq.) |
|---|---|---|
| jemison | 0.121 | 0.152 |
| clark | 0.083 | 0.092 |

La transferencia a ConvNeXt es **igual o mayor** que a ViT. Conclusión: la perturbación ILA no depende de la arquitectura ViT; produce cambios que afectan también a arquitecturas distintas. El camino **puede** alcanzar modelos cerrados de arquitectura desconocida. Descarta "cuello de transferencia entre arquitecturas".

## Limitaciones honestas

- Los números absolutos de transferencia siguen siendo modestos (juez_dist ≤ 0.12). Degradar la representación de un modelo no visto es real pero parcial.
- Esto NO demuestra que se impida una edición generativa en un modelo cerrado; mide representación, no generación.
- Muestra pequeña; se amplía para confiar en el efecto.

## Siguiente paso técnico más prometedor (justificado por evidencia)

Se descartaron con evidencia dos cuellos: bug de implementación y transferencia entre arquitecturas. El algoritmo mejoró (ILA, +76%) y transfiere cross-arquitectura. El límite restante (valores absolutos ~0.1-0.15) es plausiblemente **escala y diversidad del conjunto** (solo 4 ViT-B en CPU): este es el primer cuello demostrablemente **computacional**, no algorítmico.

1. **Escalar el conjunto en GPU gratis** (Kaggle/Colab) con ILA: más modelos y más arquitecturas (ViT-L, EVA02, ConvNeXt, SigLIP, torres de VLM). Hipótesis: la transferencia absoluta sube con la diversidad.
2. Combinar ILA con el presupuesto invisible (JND) y medir que mantiene la ventaja siendo imperceptible.
3. Validación manual en Gemini/ChatGPT de las imágenes ILA, midiendo **descripción** (no edición).
4. Evaluar por separado edición generativa y entrenamiento: son objetivos distintos no cubiertos por esto.

## RESULTADO DIRECTO EN GEMINI (definitivo, 2026-10-16)

Prueba manual: descripción de Gemini de original vs protegida-ILA, 3 retratos (protocolo en `reports/prueba_gemini/`).

| Foto | Proxy juez_dist | ¿Gemini describe peor la protegida? |
|---|---|---|
| jemison | 0.121 | No — identifica nombre, etnia, rasgos, insignias; igual que original |
| clark | 0.083 | No — nombre completo, ojos avellana, anillo de boda; igual |
| kim (control) | 0.023 | No — igual |

**Conclusión demostrada:** la mejora de ILA en los proxies (CLIP abiertos) NO se traduce en ninguna degradación de la descripción de Gemini. Cero correlación entre juez_dist y el efecto real. **La métrica proxy de distancia de embedding no predice el comportamiento de un modelo comercial.** Se abandona como objetivo. La edición generativa tampoco se frena (confirmado: Gemini puso lentes sin problema).

Implicación metodológica: hay que medir el OBJETIVO REAL (precisión de atributos en una descripción generada), no distancias de embedding, y con un VLM que genere texto, no solo un encoder.

## Giro de método: atacar la DESCRIPCIÓN, no el embedding (2026-10-16)

Tras demostrar que la distancia de embedding no predice a Gemini, se cambia de raíz:

- **Métrica:** precisión de atributos del caption generado por un VLM real, no distancia de embedding.
- **Ataque:** maximizar la pérdida de lenguaje del caption correcto bajo un VLM generativo (BLIP), teacher forcing (1 forward), + ILA en su encoder de visión + EOT + presupuesto JND invisible.
- **Transferencia:** se mide en un segundo VLM NO visto y de arquitectura distinta (ViT-GPT2).
- Infra: `engine/research/caption_lab.py`.

Señal preliminar (BLIP, atacado, 4 pasos): el caption pasó de "a young woman in a blue uniform holding a model of an airplane" a "a boy in a space suit holding a remote control device" — error de sexo, ropa y objeto. Degradación del objetivo real, no de un proxy. (El experimento completo mide la transferencia al VLM no visto, que es lo decisivo; BLIP solo demuestra que el ataque generativo funciona.)


### Resultado del ataque generativo (80 pasos, 3 imágenes)

| Foto | BLIP (atacado): atributos | ViT-GPT2 (no visto): atributos | LPIPS |
|---|---|---|---|
| jemison | 1/3 -> 0/3 (woman->boy) | 1/3 -> 0/3 (leve) | 0.177 |
| kim | 2/3 -> 0/3 ("president donald") | 1/3 -> 1/3 (igual) | 0.094 |
| chawla | 3/3 -> 1/3 | 1/3 -> 1/3 (igual) | 0.095 |

Demostrado: el ataque generativo degrada FUERTEMENTE el modelo atacado (objetivo real: caption). Pero la transferencia al VLM no visto es débil/nula (2/3 sin cambio). Mismo patrón que con embeddings: sobreajuste al modelo atacado, poca transferencia. Doble evidencia (embedding + generativo, ambos midiendo el objetivo real) de que el cuello es la TRANSFERENCIA a modelos no vistos, no la métrica ni el tipo de ataque. Visibilidad además alta (hasta 0.18). Siguiente hipótesis: atacar un ENSEMBLE de VLMs generativos diversos y medir transferencia a un VLM no visto; distingue "cuello de diversidad (computacional)" de "límite fundamental".

## Veredicto del ensemble y cierre de esta línea (evidencia)

Ataque a ensemble BLIP+GIT, medido en ViT-GPT2 (no visto): la descripción del modelo no visto queda **idéntica o casi idéntica** en los 3 casos. El ensemble no mejora la transferencia; a veces el 2º modelo atacado describe mejor (gradientes en conflicto).

**Triple evidencia convergente** (embedding ILA; generativo 1 VLM; generativo ensemble 2 VLM), más la prueba directa en Gemini: la perturbación adversarial **invisible, en CPU**, no transfiere a VLMs no vistos para degradar descripción. El cuello no es solo diversidad (el ensemble no ayudó): es un límite más fundamental de la transferencia bajo estas restricciones. Coincide con el estado del arte (VEIL: 13 modelos + GPU + ε visible logra ~50% en *caption flip*, no "describe-proof").

### Lo que la evidencia recomienda

1. **No seguir** persiguiendo perturbación invisible anti-descripción/edición de modelos comerciales en CPU: tres experimentos lo dan por agotado.
2. **Redirigir** al objetivo 3 (protección frente a ENTRENAMIENTO), que es la motivación original (Meta entrenando con fotos). Ahí las perturbaciones SÍ tienen evidencia (unlearnable examples / Nightshade) y es medible en CPU con un fine-tuning pequeño: entrenar un clasificador/adaptador con fotos limpias vs protegidas y medir si aprende peor. Objetivo separado, pérdida y métrica propias.
3. **Mantener y pulir lo que SÍ funciona, demostrado:** face-swap roto 8/8 (ArcFace), sello C2PA + marca de agua, registro de derechos firmado.
4. Para modelos comerciales, la vía realista hoy no es la perturbación sino procedencia + consentimiento + detección (SynthID, rastreo) — ya parcialmente construido.
