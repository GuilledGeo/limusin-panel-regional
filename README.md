# Limousin España — Panel regional

Panel interactivo (Streamlit) con mapas por Comunidad Autónoma/provincia de
índice de parición y espacio interpartos (año natural 2025), más "Limusin
GPT": un agente conversacional especializado en producción de ganaderías
cárnicas que responde preguntas sobre estos datos.

Los datos están congelados en el propio código (no hay conexión en vivo a
ninguna base de datos) — solo se necesita una clave de IA para el chat.

## Correr en local

```bash
pip install -r requirements.txt
cp .env.example .env   # rellenar GROQ_API_KEY (o ANTHROPIC_API_KEY)
streamlit run app/limusin_dashboard.py
```

## Desplegar en Streamlit Community Cloud

1. Ir a [share.streamlit.io](https://share.streamlit.io) → **New app**.
2. Seleccionar este repo, rama `main`, archivo principal `app/limusin_dashboard.py`.
3. En **Settings → Secrets**, pegar el contenido de `.env.example` ya
   relleno con tu clave real (formato TOML, `CLAVE = "valor"`).
4. Deploy.
