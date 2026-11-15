"""Источники данных: Steam (справочник игр) и Plati.market (предложения продавцов).

Здесь же нормализация предложений: тип (ключ / гифт / аккаунт / пополнение), платформа,
DLC, склейка с игрой и надёжность продавца. Сеня может переиспользовать это в загрузчике (S2, S3).
"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field

import httpx

UA = "SmartShopping-UrFU/1.0 (student project)"
CHEAPSHARK = "https://www.cheapshark.com/api/1.0"
CBR_URL = "https://www.cbr-xml-daily.ru/daily_json.js"
FALLBACK_USD_RATE = 85.0
STEAM_CC = "kz"  # для cc=ru Steam отдаёт success:false; цены в KZT нам не нужны, берём метаданные
TIMEOUT = httpx.Timeout(20.0, connect=10.0)

# ── нормализация ────────────────────────────────────────────────

_KIND_RULES = (
    ("пополнение", r"пополн|top[\s-]?up|robux|робукс|v-?bucks|в-?бакс|gems|кристалл|uc\b|донат|валют|wallet|кошел"),
    ("аккаунт", r"оф+лайн|offline|общий аккаунт|аккаунт|account|\bакк\b|аренд|steam guard|\bп[23]\b|п2[/-]п3"),
    ("гифт", r"\bgift\b|гифт|подар"),
    ("ключ", r"ключ|\bkey\b|cd-?key|activation|активац|🔑"),
    ("гифт", r"автодоставк|\bавто\b|выбор (региона|издания)"),  # Steam «автодоставка» — гифт другу
)
# Разделы каталога Plati, где лежат аккаунты и аренда (проверено на выдаче 01–08.11.2026):
# 22764 — аккаунты Steam, 25540 — аккаунты Steam, 22229 — аккаунты Xbox, 22380 — аккаунты/аренда PS (П2/П3).
# Разделы конкретных игр (49950 Elden Ring, 27793 Cyberpunk…) — ключи и гифты.
ACCOUNT_SECTIONS = {22764, 25540, 22229, 22380}
_PLATFORM_RULES = (
    ("Xbox", r"xbox"),
    ("PlayStation", r"\bps[345]\b|playstation|\bpsn\b"),
    ("Nintendo", r"nintendo|switch|\beshop\b"),
    ("GOG", r"\bgog\b"),
    ("Epic", r"\bepic\b|\begs\b"),
    ("EA", r"\bea app\b|origin"),
    ("Ubisoft", r"uplay|ubisoft connect"),
    ("Steam", r"steam"),
)
_DLC = re.compile(r"\bdlc\b|дополнени|season pass|сезонный абонемент|soundtrack|саундтрек|expansion|\bpack\b|набор")
# «+ DLC», «+ NEW DLC», «все DLC», Ultimate/Complete/GOTY — полная игра с дополнениями.
# Deluxe/Gold сюда не входят: «Deluxe Edition DLC» — это апгрейд без самой игры.
_FULL = re.compile(r"\+[^|/]{0,20}\bdlc|все dlc|all dlc|ultimate|полное издание|complete|goty|game of the year")

KINDS = ("ключ", "гифт", "магазин", "аккаунт", "пополнение", "другое")  # «магазин» — официальный магазин (Steam, GOG…)
PLATFORMS = tuple(p for p, _ in _PLATFORM_RULES) + ("?",)

# Регион активации из названия: порядок важен — «не для РФ» проверяем раньше «RU»
_REGION_RULES = (
    ("NO_RU", r"не для (рф|росси)|кроме (рф|росси)|no ru\b|not for ru|без рф|❌\s*ru"),
    ("RU", r"\bru\b|\bрф\b|росси|russia|\bру\b"),
    ("CIS", r"\bcis\b|снг"),
    ("KZ", r"\bkz\b|казах"),
    ("TR", r"\btr\b|турц|turkey"),
    ("EU", r"\beu\b|europe|европ"),
    ("GLOBAL", r"global|глобал|worldwide|\bмир\b|\brow\b|region free|любой регион"),
)
REGIONS_OK_RU = {"RU", "CIS", "GLOBAL"}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9а-яё]+", " ", s.lower()).strip()


def offer_region(name: str) -> str | None:
    """Регион активации по названию предложения; None — продавец не указал."""
    n = name.lower()
    for reg, pat in _REGION_RULES:
        if re.search(pat, n):
            return reg
    return None


def offer_kind(name: str, section_id: int | None = None) -> str:
    n = name.lower()
    if section_id in ACCOUNT_SECTIONS and not re.search(_KIND_RULES[0][1], n):
        return "аккаунт"
    for kind, pat in _KIND_RULES:
        if re.search(pat, n):
            return kind
    return "другое"


def offer_platform(name: str) -> str:
    n = name.lower()
    for plat, pat in _PLATFORM_RULES:
        if re.search(pat, n):
            return plat
    return "?"


def is_dlc(name: str) -> bool:
    n = name.lower()
    return bool(_DLC.search(n)) and not _FULL.search(n)


def trust(pos: int, neg: int, returns: int = 0) -> tuple[bool, float]:
    """(надёжный ли продавец, оценка 0..1). Сглаживание, чтобы 1 отзыв из 1 не давал 100%."""
    score = (pos + 1) / (pos + neg + returns + 2)
    return pos >= 5 and neg <= pos * 0.10, round(score, 3)


def matches(game_name: str, offer_name: str, exclude: list[str]) -> bool:
    """Предложение относится к игре: название входит, это не DLC и не другая игра серии.

    exclude — нормализованные названия соседних игр из Steam, длиннее искомой
    (например «elden ring nightreign» при поиске «elden ring»).
    """
    g, o = norm(game_name), norm(offer_name)
    if not g or f" {g} " not in f" {o} ":
        return False
    raw = offer_name.lower()
    for x in exclude:
        if f" {x} " not in f" {o} ":
            continue
        # «Cyberpunk 2077 + Phantom Liberty» — комплект с самой игрой, оставляем;
        # «NIGHTREIGN … RU+МИР» — плюс не перед дополнением, значит это другой товар
        extra = x[len(g):].split() if x.startswith(g) else x.split()
        if not (extra and re.search(r"\+\s*" + re.escape(extra[0]), raw)):
            return False
    return not is_dlc(offer_name)


# ── модели ──────────────────────────────────────────────────────

@dataclass
class Game:
    appid: int
    name: str
    genres: list[str]
    image: str | None
    metacritic: int | None
    release: str | None
    steam_review_pct: int | None = None
    steam_reviews: int | None = None
    dlc: list[int] = field(default_factory=list, repr=False)  # appid дополнений — для отсева в склейке


@dataclass
class Offer:
    id: str
    store: str
    title: str
    price: float
    currency: str
    url: str
    seller: str
    seller_rating: float
    sold: int
    reviews_pos: int
    reviews_neg: int
    returns: int
    kind: str
    platform: str
    trusted: bool
    trust_score: float
    image: str | None = None
    region: str | None = None      # RU / CIS / GLOBAL / KZ / TR / EU / NO_RU или None
    old_price: float | None = None  # цена без скидки (у официальных магазинов)
    note: str | None = None         # пояснение для пользователя


# ── HTTP ────────────────────────────────────────────────────────

class Sources:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self.http = client or httpx.AsyncClient(headers={"User-Agent": UA, "Accept": "application/json"},
                                                timeout=TIMEOUT, follow_redirects=True)
        self._usd: tuple[float, float] | None = None  # (время, курс)
        self._stores: dict[str, str] = {}

    async def aclose(self):
        await self.http.aclose()

    async def _json(self, url: str, params: dict, tries: int = 3):
        last: Exception | None = None
        for i in range(tries):
            try:
                r = await self.http.get(url, params=params)
                r.raise_for_status()
                return r.json()
            except (httpx.HTTPError, ValueError) as e:  # Plati периодически рвёт TLS — повторяем
                last = e
                if i + 1 < tries:  # после последней попытки не ждём
                    await asyncio.sleep(1.5 * (i + 1))
        raise SourceError(f"{url}: {last}") from last

    # Steam
    async def steam_search(self, term: str) -> list[dict]:
        data = await self._json("https://store.steampowered.com/api/storesearch/",
                                {"term": term, "cc": STEAM_CC, "l": "russian"})
        return data.get("items") or []

    async def steam_game(self, appid: int) -> Game | None:
        data = await self._json("https://store.steampowered.com/api/appdetails",
                                {"appids": appid, "cc": STEAM_CC, "l": "russian",
                                 "filters": "basic,genres,metacritic,release_date"})
        det = data.get(str(appid)) or {}
        if not det.get("success"):
            return None
        d = det["data"]
        return Game(appid=appid, name=d["name"], genres=[g["description"] for g in d.get("genres", [])],
                    image=d.get("header_image"), metacritic=(d.get("metacritic") or {}).get("score"),
                    release=(d.get("release_date") or {}).get("date"), dlc=list(d.get("dlc") or []))

    async def steam_name(self, appid: int) -> str | None:
        try:
            data = await self._json("https://store.steampowered.com/api/appdetails",
                                    {"appids": appid, "cc": STEAM_CC, "l": "english", "filters": "basic"}, tries=2)
        except SourceError:
            return None
        det = data.get(str(appid)) or {}
        return det["data"]["name"] if det.get("success") else None

    async def steam_reviews(self, appid: int) -> tuple[int | None, int | None]:
        try:
            data = await self._json(f"https://store.steampowered.com/appreviews/{appid}",
                                    {"json": 1, "language": "all", "purchase_type": "all", "num_per_page": 0}, tries=1)
        except SourceError:
            return None, None
        s = data.get("query_summary") or {}
        total = s.get("total_reviews") or 0
        return (round(100 * s.get("total_positive", 0) / total) if total else None), (total or None)

    # Plati
    async def plati_search(self, query: str, pages: int = 2) -> list[Offer]:
        out: list[Offer] = []
        for page in range(1, pages + 1):
            data = await self._json("https://plati.io/api/search.ashx",
                                    {"query": query, "pagesize": 50, "pagenum": page,
                                     "visibleOnly": "true", "response": "json"})
            for it in data.get("items", []):
                pos, neg, ret = it.get("count_positiveresponses", 0), it.get("count_negativeresponses", 0), it.get("count_returns", 0)
                ok, score = trust(pos, neg, ret)
                out.append(Offer(
                    id=f"plati:{it['id']}", store="plati.market", title=it["name"],
                    price=float(it["price_rur"]), currency="RUB", url=it["url"],
                    seller=it.get("seller_name", ""), seller_rating=float(it.get("seller_rating") or 0),
                    sold=int(it.get("numsold") or 0), reviews_pos=pos, reviews_neg=neg, returns=ret,
                    kind=offer_kind(it["name"], it.get("section_id")), platform=offer_platform(it["name"]),
                    trusted=ok, trust_score=score, image=it.get("image"), region=offer_region(it["name"]),
                ))
            if page >= int(data.get("Totalpages") or 0):
                break
        return out

    # Официальные магазины через CheapShark (Steam, GOG, Humble, Fanatical, GMG…), цены в $
    async def usd_rate(self) -> tuple[float, bool]:
        """Курс доллара ЦБ РФ (кэш 6 ч). (курс, получен ли он сейчас от ЦБ)."""
        if self._usd and time.monotonic() - self._usd[0] < 6 * 3600:
            return self._usd[1], True
        try:
            data = await self._json(CBR_URL, {}, tries=1)
            rate = float(data["Valute"]["USD"]["Value"])
        except (SourceError, KeyError, TypeError, ValueError):
            return FALLBACK_USD_RATE, False
        self._usd = (time.monotonic(), rate)
        return rate, True

    async def cheapshark_stores(self) -> dict[str, str]:
        if not self._stores:
            try:
                data = await self._json(f"{CHEAPSHARK}/stores", {}, tries=1)
                self._stores = {str(s["storeID"]): s["storeName"] for s in data if s.get("isActive", 1)}
            except (SourceError, KeyError, TypeError):
                return {}
        return self._stores

    async def official_offers(self, game: Game) -> tuple[list[Offer], list[str]]:
        """Самая низкая цена игры в каждом официальном магазине. Ошибка — пустой список и предупреждение."""
        try:
            deals = await self._json(f"{CHEAPSHARK}/deals", {"steamAppID": game.appid, "pageSize": 60}, tries=2)
        except SourceError:
            return [], ["Официальные магазины (CheapShark) не ответили — показаны только продавцы Plati"]
        if not isinstance(deals, list) or not deals:
            return [], []
        stores = await self.cheapshark_stores()
        rate, fresh = await self.usd_rate()
        warnings = [] if fresh else [f"Курс ЦБ недоступен — цены в $ пересчитаны по {FALLBACK_USD_RATE} ₽"]
        best: dict[str, dict] = {}
        for d in deals:
            try:
                sid, price = str(d["storeID"]), float(d["salePrice"])
            except (KeyError, TypeError, ValueError):
                continue
            if sid not in best or price < float(best[sid]["salePrice"]):
                best[sid] = d
        out = []
        for sid, d in best.items():
            name = stores.get(sid, f"Магазин #{sid}")
            plat = "GOG" if "gog" in name.lower() else "Epic" if "epic" in name.lower() else "Steam"
            usd, usd_old = float(d["salePrice"]), float(d.get("normalPrice") or d["salePrice"])
            out.append(Offer(
                id=f"{norm(name).replace(' ', '-')}:{game.appid}", store=name, title=f"{d.get('title') or game.name} — {name}",
                price=round(usd * rate), currency="RUB", url=f"https://www.cheapshark.com/redirect?dealID={d['dealID']}",
                seller=name, seller_rating=0, sold=0, reviews_pos=0, reviews_neg=0, returns=0,
                kind="магазин", platform=plat, trusted=True, trust_score=1.0, image=d.get("thumb"), region="GLOBAL",
                old_price=round(usd_old * rate) if usd_old > usd else None,
                note=f"Официальный магазин: ${usd:.2f} по курсу ЦБ {rate:.2f} ₽, оплата зарубежной картой",
            ))
        return sorted(out, key=lambda o: o.price), warnings

    async def top_games(self, n: int = 50) -> list[int]:
        """appid самых популярных игр Steam (в топе много бесплатных — их отсеет загрузчик)."""
        data = await self._json("https://api.steampowered.com/ISteamChartsService/GetMostPlayedGames/v1/", {}, tries=2)
        return [r["appid"] for r in (data.get("response") or {}).get("ranks", [])][:n]


class SourceError(RuntimeError):
    pass
