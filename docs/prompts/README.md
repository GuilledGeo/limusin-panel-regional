# Prompts de Limusin GPT — versionados y por capacidad de modelo

Esta carpeta contiene los prompts que usa `app/limusin_dashboard.py` como
archivos `.md` sueltos (no como f-strings enterrados en el código), para
poder leerlos, revisarlos y ajustarlos sin tocar Python, y para poder tener
una versión distinta según qué tan capaz sea el modelo de IA activo.

## Archivos

| Archivo | Para qué | Se usa con |
|---|---|---|
| `limusin_gpt_system_prompt.md` | System prompt del chat "Limusin GPT" (persona, datos, reglas 1-9) | Cualquier modelo — no ha mostrado necesitar variantes por tier |
| `recomendaciones_prompt_small_model.md` | Prompt del panel de Recomendaciones, con TODAS las guardas necesarias para un modelo pequeño | Modelos "small" (ver tabla de tiers abajo) |
| `recomendaciones_prompt_large_model.md` | Misma tarea, sin las guardas específicas para limitaciones de modelo pequeño | Modelos "large" |

## Por qué dos versiones de "Recomendaciones" y no del chat

El panel de Recomendaciones (`generate_ai_recommendations_v2` en
`app/limusin_dashboard.py`) le pide al modelo que **busque y decida por sí
mismo** qué regiones destacar — es la tarea donde más se notó la diferencia
de capacidad entre modelos durante las pruebas de esta sesión (ver
[`../prompt_recomendaciones_panel.md`](../prompt_recomendaciones_panel.md)
para el historial completo de fallos encontrados). El chat, en cambio,
solo tiene que responder preguntas puntuales del usuario sobre datos ya
dados — una tarea más simple donde no hizo falta parchear el prompt por
tier de modelo.

Diferencias concretas entre `..._small_model.md` y `..._large_model.md`:

- **`pct_menos_365d`**: prohibida en la versión `small` (el modelo pequeño
  la interpretaba al revés de forma sistemática); permitida en `large` con
  solo la definición correcta, confiando en que un modelo más capaz la
  interprete bien.
- **Chequeo de auto-verificación explícito** (releer la fila completa,
  comparar con 2-3 filas más antes de escribir): presente en `small`,
  resumido a una frase en `large` — un modelo más capaz necesita menos
  andamiaje de este tipo.
- El resto de reglas (formato, comparativas explícitas, no mezclar CCAA
  con provincia, sin puntos suspensivos) son iguales en ambas — son reglas
  de negocio/estilo, no parches por limitación de modelo.

## Cómo se elige el archivo (`MODEL_TIERS` en `limusin_dashboard.py`)

```python
MODEL_TIERS = {
    "llama-3.1-8b-instant": "small",       # el que se usa hoy (cuota gratuita alta)
    "llama-3.3-70b-versatile": "large",    # el que se usó antes de tener que bajar por rate limit
    "claude-sonnet-4-6": "large",
    # cualquier modelo NO listado aquí -> "small" por defecto (más prudente
    # asumir limitado que asumir capaz sin haberlo probado)
}
```

`_current_model_tier()` mira `GROQ_MODEL` o `ANTHROPIC_MODEL` (según
`AI_PROVIDER`) contra esta tabla y decide qué `.md` cargar. **Si en el
futuro se cambia de modelo (a un Groq más grande, u otro proveedor), solo
hay que añadir esa entrada a `MODEL_TIERS` — el código no necesita
tocarse, y el prompt correcto se selecciona solo.**

Además, el panel de Recomendaciones solo permite IA a nivel CCAA cuando el
tier es `small` (a nivel provincia, con 39 filas, el modelo pequeño mostró
mucha más tasa de error — ver el historial en
`../prompt_recomendaciones_panel.md`). Con tier `large`, la IA se puede
usar también a nivel provincia.

## Cómo se cargan (`_load_prompt_md` en `limusin_dashboard.py`)

Los archivos se leen del disco con `@st.cache_data` (se cachean tras la
primera lectura, no hay overhead de I/O repetido) y se rellenan con
`.format(...)` — cada archivo documenta arriba qué placeholders espera
(`{nivel_txt}`, `{variante}`, `{df_ccaa}`, etc.).

## Si vas a editar un prompt

- Cambios de negocio/estilo (tono, formato, qué debe cubrir la respuesta):
  edítalos igual en `small` y `large` para que no diverjan sin motivo.
- Cambios de "parche para limitación de modelo" (prohibir una columna
  confusa, añadir un chequeo extra): solo en `small`, y evalúa si de
  verdad hace falta también en `large` antes de copiarlo sin más.
- Después de cualquier cambio, prueba con una llamada real (ver el patrón
  de smoke tests en `log_diario.md`, sección de Recomendaciones) antes de
  dar el cambio por bueno — los prompts de este proyecto han fallado de
  formas no obvias más de una vez.
