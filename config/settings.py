import os

from dotenv import load_dotenv

load_dotenv()

# Proveedor de IA para Limusin GPT. "groq" es gratuito; "gemini" (cuenta de
# empresa) o "anthropic" son opciones más capaces — cambiarlo no requiere
# tocar más código.
AI_PROVIDER = os.getenv("AI_PROVIDER", "groq")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Gemini (Google AI Studio — cuenta de empresa con acceso de pago)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
