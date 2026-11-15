"""ShopNLU — своя маленькая нейросеть для разбора запросов покупателей игр (работает на numpy).

Архитектура (обучение — app/nlu/train.py на PyTorch):
  слово → среднее эмбеддингов его хэшей (слово, n-граммы 3–5, форма), 48 чисел
  → двунаправленная GRU (2 × 64)
  → для каждого слова: метка O / B-GAME / I-GAME / B-PRICE / I-PRICE / B-GENRE / I-GENRE (декодер Витерби)
  → для всего запроса (max+mean по словам): намерение, тип товара, платформа.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from .features import INTENTS, KINDS, PLATFORMS, TAGS, prep, sentence_feats, tokenize
from .lexicon import ALIASES, genre_stem, parse_price

MODEL_DIR = Path(__file__).resolve().parent
WEIGHTS = MODEL_DIR / "shopnlu.npz"
META = MODEL_DIR / "shopnlu.json"


@dataclass
class Frame:
    """Что модель поняла из запроса."""
    intent: str
    confidence: float
    kind: str | None              # None — тип не указан
    platform: str | None
    game: str | None              # как написал пользователь
    max_price: float | None
    genre: str | None             # корень жанра для поиска в жанрах Steam («ролев», «инди»…)
    genre_text: str | None = None
    query: str | None = None      # что искать в магазинах (после словаря и сверки с каталогом)
    tokens: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    probs: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        d = asdict(self)
        d.pop("tokens"), d.pop("tags"), d.pop("probs")
        return d


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def _softmax(x):
    e = np.exp(x - x.max(-1, keepdims=True))
    return e / e.sum(-1, keepdims=True)


# допустимые переходы BIO: I-X только после B-X или I-X
_ALLOWED = np.ones((len(TAGS), len(TAGS)), dtype=bool)
for j, t in enumerate(TAGS):
    if t.startswith("I-"):
        for i, s in enumerate(TAGS):
            _ALLOWED[i, j] = s[2:] == t[2:] and s != "O"
_START_OK = np.array([not t.startswith("I-") for t in TAGS])


def viterbi(logp: np.ndarray) -> list[int]:
    T, n = logp.shape
    score = np.where(_START_OK, logp[0], -1e9)
    back = np.zeros((T, n), dtype=int)
    trans = np.where(_ALLOWED, 0.0, -1e9)
    for t in range(1, T):
        cand = score[:, None] + trans
        back[t] = cand.argmax(0)
        score = cand.max(0) + logp[t]
    path = [int(score.argmax())]
    for t in range(T - 1, 0, -1):
        path.append(int(back[t, path[-1]]))
    return path[::-1]


class ShopNLU:
    def __init__(self, weights: Path = WEIGHTS, meta: Path = META):
        w = np.load(weights)
        self.w = {k: w[k].astype(np.float32) for k in w.files}
        self.meta = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}
        self.H = self.w["gru_f_whh"].shape[1]

    def _gru(self, x: np.ndarray, d: str, reverse: bool) -> np.ndarray:
        """Один проход GRU — те же формулы, что у torch.nn.GRU (порядок вентилей r, z, n)."""
        H, w = self.H, self.w
        gi = x @ w[f"gru_{d}_wih"].T + w[f"gru_{d}_bih"]
        whh, bhh = w[f"gru_{d}_whh"], w[f"gru_{d}_bhh"]
        h = np.zeros(H, dtype=np.float32)
        out = np.zeros((len(x), H), dtype=np.float32)
        for t in (range(len(x) - 1, -1, -1) if reverse else range(len(x))):
            gh = whh @ h + bhh
            r = _sigmoid(gi[t, :H] + gh[:H])
            z = _sigmoid(gi[t, H:2 * H] + gh[H:2 * H])
            n = np.tanh(gi[t, 2 * H:] + r * gh[2 * H:])
            h = (1 - z) * n + z * h
            out[t] = h
        return out

    def forward(self, words: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        ids = np.array(sentence_feats(words))                       # T × K
        emb = self.w["emb"][ids]                                    # T × K × D (строка 0 — нули)
        cnt = np.maximum((ids > 0).sum(1, keepdims=True), 1)
        x = emb.sum(1) / cnt                                        # T × D
        h = np.concatenate([self._gru(x, "f", False), self._gru(x, "b", True)], 1)  # T × 2H
        pooled = np.concatenate([h.max(0), h.mean(0)])
        tag = h @ self.w["tag_w"].T + self.w["tag_b"]
        heads = [pooled @ self.w[f"{k}_w"].T + self.w[f"{k}_b"] for k in ("intent", "kind", "platform")]
        return tag, *heads

    def parse(self, text: str) -> Frame:
        toks = tokenize(text)
        words = [t for t, _, _ in toks]
        if not words:
            return Frame("other", 1.0, None, None, None, None, None)
        tag_logits, il, kl, pl = self.forward(words)
        tags = [TAGS[i] for i in viterbi(np.log(_softmax(tag_logits) + 1e-9))]
        ip, kp, pp = _softmax(il), _softmax(kl), _softmax(pl)
        intent = INTENTS[int(ip.argmax())]
        kind = KINDS[int(kp.argmax())]
        plat = PLATFORMS[int(pp.argmax())]
        spans = _spans(tags)
        original = text.replace("ё", "е")
        game = genre = genre_text = None
        price = None
        if "GAME" in spans:
            a, b = max(spans["GAME"], key=lambda s: s[1] - s[0])  # самый длинный кусок
            game = original[toks[a][1]:toks[b - 1][2]].strip()
        if "PRICE" in spans:
            a, b = spans["PRICE"][0]
            price = parse_price(words[a:b])
        if "GENRE" in spans:
            a, b = spans["GENRE"][0]
            genre_text = " ".join(words[a:b])
            genre = genre_stem(words[a:b])
        return Frame(
            intent=intent, confidence=round(float(ip.max()), 3),
            kind=None if kind == "any" or kp.max() < 0.5 else kind,
            platform=None if plat == "any" or pp.max() < 0.5 else plat,
            game=game, max_price=price, genre=genre, genre_text=genre_text, tokens=words, tags=tags,
            probs={"intent": {k: round(float(v), 3) for k, v in zip(INTENTS, ip)}},
        )


def _spans(tags: list[str]) -> dict[str, list[tuple[int, int]]]:
    out: dict[str, list[tuple[int, int]]] = {}
    start = None
    for i, t in enumerate(tags + ["O"]):
        if start is not None and not t.startswith("I-"):
            out.setdefault(tags[start][2:], []).append((start, i))
            start = None
        if t.startswith("B-"):
            start = i
    return out


# ── как искать то, что назвал пользователь ──────────────────────

def _n(s: str) -> str:
    return re.sub(r"[^a-z0-9а-я']+", " ", prep(s)).strip()


def _trigrams(s: str) -> set[str]:
    s = f"  {s} "
    return {s[i:i + 3] for i in range(len(s) - 2)}


def resolve(game: str, titles: list[str] = ()) -> str:
    """«гта 5» → «Grand Theft Auto V»; «elden rign» → «ELDEN RING» из каталога; иначе как есть."""
    g = _n(game)
    if g in ALIASES:
        return ALIASES[g]
    words = g.split()
    for k in range(len(words) - 1, 0, -1):  # «гта 5 премиум» — словарь по началу
        head = " ".join(words[:k])
        if head in ALIASES and len(head) > 2:
            return ALIASES[head] + " " + " ".join(words[k:])
    best, score = None, 0.0
    tg = _trigrams(g)
    for t in titles:  # исправляем опечатки: столько же слов и те же цифры («hades 2» ≠ «Hades»)
        nt = _n(t)
        if nt == g:
            return t
        if len(nt.split()) != len(words) or re.findall(r"\d+", nt) != re.findall(r"\d+", g):
            continue
        tt = _trigrams(nt)
        s = len(tg & tt) / max(len(tg | tt), 1)
        if s > score:
            best, score = t, s
    return best if best and score >= 0.5 else game


_model: ShopNLU | None = None


def available() -> bool:
    return WEIGHTS.exists()


def get() -> ShopNLU:
    global _model
    if _model is None:
        _model = ShopNLU()
    return _model
