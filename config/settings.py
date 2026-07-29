import os

from dotenv import load_dotenv

load_dotenv()

# Proveedor de IA para Limusin GPT. "groq" es gratuito; "anthropic" es el
# objetivo de producción — cambiarlo no requiere tocar más código.
AI_PROVIDER = os.getenv("AI_PROVIDER", "groq")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
