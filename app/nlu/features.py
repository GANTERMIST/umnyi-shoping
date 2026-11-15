"""Токенизация и признаки слов для модели ShopNLU — общие для обучения (PyTorch) и работы (numpy).

Слово превращается в набор хэшей (как в fastText): само слово, символьные n-граммы 3–5 и «форма»
(цифры/латиница/кириллица). Поэтому модель понимает опечатки и падежи («стим», «стиме», «стима»)
и незнакомые названия игр.
"""
from __future__ import annotations

import re
import zlib

BUCKETS = 1 << 14   # размер таблицы эмбеддингов; 0 — заполнитель
MAX_FEATS = 24      # признаков на слово (лишние n-граммы отбрасываются)

TAGS = ["O", "B-GAME", "I-GAME", "B-PRICE", "I-PRICE", "B-GENRE", "I-GENRE"]
INTENTS = ["buy", "recommend", "review", "compare", "faq", "greet", "other"]
KINDS = ["any", "ключ", "гифт", "аккаунт", "пополнение", "магазин"]
PLATFORMS = ["any", "Steam", "Xbox", "PlayStation", "Nintendo", "Epic", "GOG"]

_TOKEN = re.compile(r"[a-zа-я0-9]+(?:(?:['’.]|(?<=\d),(?=\d))[a-zа-я0-9]+)*")


def prep(text: str) -> str:
    """Нижний регистр, ё→е. Длина строки не меняется — позиции токенов совпадают с исходным текстом."""
    return text.lower().replace("ё", "е")


def tokenize(text: str) -> list[tuple[str, int, int]]:
    """[(токен, начало, конец)] — знаки препинания отбрасываются, «ps5», «1.5к», «baldur's» — одно слово."""
    return [(m.group(), m.start(), m.end()) for m in _TOKEN.finditer(prep(text))]


def _h(s: str) -> int:
    return zlib.crc32(s.encode("utf-8")) % (BUCKETS - 1) + 1


def shape(w: str) -> str:
    s = re.sub(r"[0-9]+", "0", w)
    s = re.sub(r"[a-z]+", "a", s)
    return re.sub(r"[а-я]+", "я", s)


def word_feats(w: str) -> list[int]:
    feats = [_h("w:" + w), _h("s:" + shape(w))]
    padded = f"<{w}>"
    for n in (3, 4, 5):
        for i in range(len(padded) - n + 1):
            feats.append(_h(f"{n}:{padded[i:i + n]}"))
            if len(feats) >= MAX_FEATS:
                return feats
    return feats


def sentence_feats(tokens: list[str]) -> list[list[int]]:
    """Матрица T×MAX_FEATS (дополнена нулями)."""
    out = []
    for w in tokens:
        f = word_feats(w)
        out.append(f + [0] * (MAX_FEATS - len(f)))
    return out
