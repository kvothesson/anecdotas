# Procesamiento masivo de video con LLM — Aprendizajes

**Proyecto**: Anécdotas Explorer — catalogación de 271 episodios de YouTube  
**Fecha**: Abril 2026  
**Stack**: yt-dlp + Claude + GitHub Pages

---

## El pipeline que funcionó

```
YouTube → yt-dlp → {VIDEO_ID}_raw.json → Claude (análisis) → {VIDEO_ID}.json → index.json
```

La separación en dos etapas (fetch y análisis) fue la decisión más importante. Si el análisis falla, no hay que re-descargar. Si la descarga falla, no hay que re-analizar.

---

## Fase 1 — Claude Code skill (episodios 1-30)

**Estrategia**: Procesar episodio por episodio dentro de una conversación de Claude Code usando una skill dedicada.

**Resultado observado** (timestamps de archivos):
- Velocidad: ~1.6 min/episodio en tiempo activo
- Límite real: ~14-16 episodios por sesión antes de cortar
- Gap entre sesiones: ~5 horas (límite de Claude Code)
- 4 sesiones para ~45 episodios a lo largo de un día completo

**Ventajas**:
- Costo $0
- Forzó a validar el pipeline y el schema antes de escalar
- Detectó edge cases temprano (normalización de geografía, números de episodio)

**Desventajas**:
- Tiempo de reloj proyectado para 271 episodios: **4-7 días** con gaps reales de vida
- Incluso sin límites: **~7 horas** de tiempo activo puro (7.5x más lento que la API)
- Alta fricción: hay que retomar el contexto múltiples veces

---

## Fase 2 — API directa (episodios 31-271)

**Estrategia**: Bulk script que llama a la API de Claude directamente, sin interfaz conversacional.

**Resultado real** (timestamps de archivos):
- 228 episodios procesados entre las 00:00 y las 00:57 del 26 de abril
- **57 minutos continuos, sin interrupciones**
- Velocidad: ~4 episodios por minuto
- Costo total: **$4.16** → ~$0.018 por episodio

---

## Comparación final

| Métrica | Claude Code (skill) | API directa |
|---|---|---|
| Episodios | ~45 | ~228 |
| Tiempo activo | ~7 horas (proyectado para 271) | 57 minutos |
| Tiempo de reloj | 4-7 días | 57 minutos |
| Costo | $0 | $4.16 |
| Fricción | Alta | Ninguna |
| Factor de velocidad | 7.5x más lento | baseline |

---

## Aprendizajes técnicos

**yt-dlp**
- `--skip-download` es clave: baja solo subtítulos y metadata, de minutos a segundos por video
- Los subtítulos auto-generados de YouTube son suficientes para análisis semántico en español
- El formato VTT tiene ruido masivo (timestamps, HTML, duplicados por sliding window) — necesita parser con deduplicación por `seen set`, sino el transcript tiene 3x el texto real

**LLM para análisis**
- El transcript no necesita ser perfecto — el modelo infiere contexto con errores de transcripción
- Schema controlado con vocabulario fijo (`categories`, `emotional_arc`, `era`, etc.) es indispensable a escala — sin esto aparecen "años 90", "los 90", "década del 90" como tres valores distintos
- La normalización de geografía requiere un pass explícito — el modelo no es consistente en nombres de lugares a través de cientos de episodios
- Un episodio de ~10 minutos cabe cómodamente en contexto, el análisis es barato en tokens

**Arquitectura del producto**
- Separar `index.json` (sin transcripts) del JSON individual por episodio mantiene el payload inicial pequeño
- Eliminar los transcripts del repo fue la decisión correcta — no aportan al frontend y pesan en git
- Sin build step = sin fricción para iterar

---

## El patrón estratégico

```
Fase gratis (Claude Code / skill)
  → valida el pipeline
  → define y ajusta el schema
  → detecta edge cases
  → costo: tiempo, pero tiempo bien invertido

Fase paga (API directa)
  → escala el bulk una vez que el pipeline está probado
  → costo: mínimo en dinero, mínimo en tiempo
```

**No saltarse la Fase 1.** Los $4 de la Fase 2 fueron baratos *porque* la Fase 1 ya había resuelto los problemas. Escalar con un schema roto hubiera costado más en correcciones que lo ahorrado.

---

## Los números que lo resumen

**El proyecto completo** (frontend + pipeline + 271 episodios):
- Tiempo de reloj: ~10 horas 25 minutos (14:06 del 25/04 al 00:31 del 26/04)
- Tiempo activo real: ~5-6 horas (descontando 4h 46min de pausa por límite de sesión)

**Solo el procesamiento de los 271 episodios**:
> Catalogar 271 videos de YouTube con análisis semántico completo — categorías, arquetipos, era, intensidad, giro narrativo — costó **$4.16 y menos de 2 horas** sumando ambas fases.  
> El equivalente en tiempo humano a 5 minutos por episodio sería **22 horas de trabajo**.

---

## Cuánto tiempo ahorró cada capa

| Escenario | Tiempo estimado | Ahorro vs lo realizado |
|---|---|---|
| Todo manual (mirar video + escribir análisis) | ~135 hs | **129 horas** |
| Con transcripts, sin IA | ~45 hs | **39 horas** |
| Con IA, sin pipeline automatizado | ~22 hs | **16 horas** |
| **Pipeline automatizado + API (lo realizado)** | **~6 hs** | — |

El mayor salto no fue la IA — fue **automatizar el pipeline**. Pasar de "IA manual" a "pipeline + API" ahorró más tiempo que pasar de "sin IA" a "IA manual".

La IA sin automatización sigue siendo trabajo. La automatización sin IA hubiera sido imposible para el análisis semántico. Los dos juntos son donde está el multiplicador real.
