"""Точка входа для Vercel: Python-функция отдаёт то же FastAPI-приложение, что и локальный запуск."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402,F401
