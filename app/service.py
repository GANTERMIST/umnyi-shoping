"""Логика поиска: Steam + Plati + официальные магазины в реальном времени, кэш и база (SQLite).

Каждый живой поиск и загрузчик (app/loader.py) пишут игры, предложения и историю цен в базу.
Если источники не отвечают — отвечаем из базы с предупреждением.
"""
from __future__ import annotations

import asyncio
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from . import sources as src
from .db import Database
from .schemas import CatalogItem, Facets, GameCardOut, GameOut, HistoryOut, OfferOut, PricePoint, SearchOut


class TTLCache:
    def __init__(self, ttl: float):
        self.ttl, self.data = ttl, {}

    def get(self, key):
        v = self.data.get(key)
        if v and time.monotonic() - v[0] < self.ttl:
            return v[1]
        return None

    def put(self, key, value):
        self.data[key] = (time.monotonic(), value)


def _game_out(g: src.Game | None) -> GameOut | None:
    if not g:
        return None
    d = asdict(g)
    d.pop("dlc", None)
    return GameOut(**d)


def offer_out(o: src.Offer) -> OfferOut:
    return OfferOut(**asdict(o))


def _sort(offers: list[src.Offer], sort: str) -> list[src.Offer]:
    if sort == "trust":
        return sorted(offers, key=lambda o: (-o.trusted, -o.trust_score, o.price))
    if sort == "sold":
        return sorted(offers, key=lambda o: (-o.sold, o.price))
    return sorted(offers, key=lambda o: (not o.trusted, o.price))  # надёжные дешёвые — первыми


class Service:
    def __init__(self, sources: src.Sources, data_dir: Path, ttl: float = 900, dlc_limit: int = 15):
        self.src = sources
        self.cache = TTLCache(ttl)
        self.db = Database(data_dir / "shop.db")
        self.history = self.db  # старое имя: history.db — соединение SQLite
        self.dlc_names: dict[int, list[str]] = {}
        self.dlc_limit = dlc_limit

    async def _resolve(self, query: str) -> tuple[src.Game | None, list[str]]:
        """Игра из Steam + названия «соседей» по серии, которые надо исключить."""
        items = await self.src.steam_search(query)
        if not items:
            return None, []
        q = src.norm(query)
        best = next((it for it in items if src.norm(it["name"]) == q), items[0])
        if q and q not in src.norm(best["name"]) and src.norm(best["name"]) not in q:
            return None, []  # Steam нашёл что-то не то (например, по запросу «робуксы»)
        game = await self.src.steam_game(best["id"])
        if not game:
            return None, []
        g = src.norm(game.name)
        neighbors = {src.norm(it["name"]) for it in items if it["id"] != game.appid}
        exclude = {n for n in neighbors if g in n and n != g}
        exclude |= {src.norm(n) for n in await self._dlc_names(game) if src.norm(n) != g}
        return game, sorted(exclude, key=len, reverse=True)

    async def _dlc_names(self, game: src.Game) -> list[str]:
        if game.appid not in self.dlc_names:
            names = await asyncio.gather(*(self.src.steam_name(i) for i in game.dlc[:self.dlc_limit]))
            self.dlc_names[game.appid] = [n for n in names if n]
        return self.dlc_names[game.appid]

    async def _steam_and_official(self, query: str):
        game, exclude = await self._resolve(query)
        official, warns = (await self.src.official_offers(game)) if game else ([], [])
        return game, exclude, official, warns

    async def _collect(self, query: str, fresh: bool = False):
        """(игра, все предложения магазинов, относящиеся к игре, предупреждения)."""
        key = src.norm(query)
        cached = None if fresh else self.cache.get(key)
        if cached:
            return cached
        warnings: list[str] = []
        steam_task = asyncio.create_task(self._steam_and_official(query))
        plati_ok = True
        try:
            offers = await self.src.plati_search(query)
        except src.SourceError:
            offers, plati_ok = [], False
        try:
            game, exclude, official, w = await steam_task
            warnings += w
        except src.SourceError:
            game, exclude, official = None, [], []
            warnings.append("Steam не ответил — показываем предложения без карточки игры")
        if game:  # продавцы пишут то по-английски, то по-русски — подходит любое из названий
            names = {game.name, query}
            matched = [o for o in offers if any(src.matches(n, o.title, exclude) for n in names)]
        else:  # не Steam-товар (пополнения и т.п.) — все слова запроса должны быть в названии
            words = [w for w in src.norm(query).split() if len(w) > 2]
            matched = [o for o in offers if all(w in src.norm(o.title) for w in words)] or offers
        matched += official
        offers += official

        if not plati_ok:  # офлайн-режим: берём сохранённые предложения Plati из базы
            row = self.db.product_by_appid(game.appid) if game else self.db.find_product(query)
            saved = [o for o in self.db.offers_for(row["id"]) if o.store == "plati.market"] if row else []
            if saved:
                game = game or Database.game(row)
                matched, offers = saved + matched, saved + offers
                warnings.insert(0, f"Plati.market не ответил — цены продавцов из базы на {row['updated_at'][:16].replace('T', ' ')} UTC")
            else:
                warnings.insert(0, "Plati.market не ответил — попробуйте ещё раз через минуту")

        if plati_ok or official:
            pid = self.db.save_game(game) if game else None
            self.db.save_offers(pid, [o for o in matched if plati_ok or o.kind == "магазин"])
        result = (game, offers, matched, warnings)
        if plati_ok and offers:  # ошибки не кэшируем
            self.cache.put(key, result)
        return result

    async def search(self, query: str, kinds: list[str] | None = None, platforms: list[str] | None = None,
                     max_price: float | None = None, trusted_only: bool = False,
                     sort: str = "price", limit: int = 50, stores: list[str] | None = None) -> SearchOut:
        game, offers, matched, warnings = await self._collect(query)
        facets = Facets(kinds=dict(Counter(o.kind for o in matched)), platforms=dict(Counter(o.platform for o in matched)))
        res = [o for o in matched
               if (not kinds or o.kind in kinds)
               and (not platforms or o.platform in platforms)
               and (not stores or o.store in stores)
               and (max_price is None or o.price <= max_price)
               and (not trusted_only or o.trusted)]
        res = _sort(res, sort)[:limit]
        if game and game.steam_review_pct is None:
            game.steam_review_pct, game.steam_reviews = await self.src.steam_reviews(game.appid)
            if game.steam_review_pct is not None:
                self.db.save_game(game)
        return SearchOut(query=query, game=_game_out(game), total_found=len(offers), matched=len(matched),
                         facets=facets, offers=[offer_out(o) for o in res], warnings=warnings)

    async def game_card(self, appid: int) -> GameCardOut | None:
        try:
            game = await self.src.steam_game(appid)
        except src.SourceError:
            row = self.db.product_by_appid(appid)
            if not row:
                raise
            game = Database.game(row)
        if not game:
            return None
        found = await self.search(game.name, sort="price", limit=200)
        g = found.game if found.game and found.game.appid == appid else _game_out(game)
        if g.steam_review_pct is None:
            g.steam_review_pct, g.steam_reviews = await self.src.steam_reviews(appid)
        best: dict[str, OfferOut] = {}
        for o in found.offers:
            if o.trusted and o.kind not in best:
                best[o.kind] = o
        return GameCardOut(game=g, offers=found.offers, best=best)

    async def refresh(self, appid: int) -> tuple[str, int]:
        """Для загрузчика: свежие цены игры в базу. (название, сколько предложений)."""
        game = await self.src.steam_game(appid)
        if not game:
            return f"#{appid} (нет в Steam)", 0
        _, _, matched, _ = await self._collect(game.name, fresh=True)
        if game.steam_review_pct is None:
            game.steam_review_pct, game.steam_reviews = await self.src.steam_reviews(appid)
            self.db.save_game(game)
        return game.name, len(matched)

    def price_history(self, offer_id: str) -> HistoryOut:
        return HistoryOut(offer_id=offer_id, points=[PricePoint(ts=ts, price=p) for ts, p in self.db.points(offer_id)])

    def catalog(self, limit: int) -> list[CatalogItem]:
        return [CatalogItem(**c) for c in self.db.catalog(limit)]

    def deals(self, limit: int) -> list[CatalogItem]:
        return [CatalogItem(**c) for c in self.db.deals(limit)]

    def current(self, ids: list[str]) -> list[OfferOut]:
        return [offer_out(o) for o in self.db.current(ids)]
