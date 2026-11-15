"""Загрузчик цен в базу: топ игр Steam + запасной список популярных платных игр.

    python -m app.loader                      # один проход по ~50 играм
    python -m app.loader --top 20             # меньше игр
    python -m app.loader --games "elden ring" "hades"
    python -m app.loader --every-hours 24     # по расписанию (раз в сутки), Ctrl+C — остановить

Steam ограничивает ~200 запросов за 5 минут, поэтому между играми пауза, а названий DLC берём не больше 3.
Если источник не ответил — старая цена в базе остаётся (ничего не затираем).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from .service import Service
from .sources import SourceError, Sources

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("loader")

# Популярные платные игры — если чарт Steam недоступен или в нём одни бесплатные
FALLBACK_APPIDS = [
    1245620, 1091500, 1086940, 1174180, 271590, 292030, 990080, 413150, 105600, 1145360,
    814380, 374320, 252490, 892970, 1623730, 553850, 1593500, 1551360, 2050650, 367520,
    2246340, 2358720, 289070, 227300, 221100, 381210, 526870, 427520, 294100, 108600,
    1966720, 1426210, 1222140, 1771300, 489830, 377160, 782330, 264710, 242760, 1326470,
    739630, 1144200, 394360, 255710, 261550, 275850,
]
PAUSE = 3.0


async def run_once(svc: Service, appids: list[int] | None = None, queries: list[str] | None = None, top: int = 50) -> int:
    if queries:
        targets: list[int | str] = list(queries)
    else:
        if appids is None:
            try:
                charts = await svc.src.top_games(100)
            except SourceError:
                charts = []
                log.warning("чарт Steam недоступен — беру запасной список")
            appids = list(dict.fromkeys(charts + FALLBACK_APPIDS))
        targets = list(appids)
    done = 0
    for i, t in enumerate(targets):
        if done >= top:
            break
        try:
            if isinstance(t, str):
                res = await svc.search(t)
                name, n = (res.game.name if res.game else t), res.matched
            else:
                name, n = await svc.refresh(t)
        except SourceError as e:
            log.warning("[%d] %s: источник не ответил (%s) — старые цены оставлены", i + 1, t, e)
            await asyncio.sleep(PAUSE * 2)
            continue
        if n:
            done += 1
            log.info("[%d/%d] %s — %d предложений", done, top, name, n)
        else:
            log.info("пропуск: %s (бесплатная или нет предложений)", name)
        await asyncio.sleep(PAUSE)
    return done


async def main() -> None:
    p = argparse.ArgumentParser(description="Загрузчик цен «Умного Шопинга»")
    p.add_argument("--top", type=int, default=50, help="сколько игр с предложениями загрузить")
    p.add_argument("--games", nargs="*", help="названия игр вместо топа")
    p.add_argument("--every-hours", type=float, default=0, help="повторять каждые N часов")
    a = p.parse_args()
    load_dotenv(ROOT / ".env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    sources = Sources()
    svc = Service(sources, Path(os.getenv("DATA_DIR", ROOT / "data")), dlc_limit=3)
    try:
        while True:
            n = await run_once(svc, queries=a.games, top=a.top if not a.games else len(a.games))
            log.info("готово: %d игр в базе обновлено", n)
            if not a.every_hours:
                break
            log.info("следующий проход через %.1f ч", a.every_hours)
            await asyncio.sleep(a.every_hours * 3600)
    finally:
        await sources.aclose()


if __name__ == "__main__":
    asyncio.run(main())
