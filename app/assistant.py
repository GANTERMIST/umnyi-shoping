"""Помощник: «где выгоднее купить X» → подбор предложений → ответ.

Три режима (ASSISTANT_ENGINE):
  model  — по умолчанию: своя обученная модель ShopNLU разбирает запрос (app/nlu), ответ собирает app/smart.py;
  rules  — разбор регулярками и ответ по шаблону (если весов модели нет);
  claude — внешний Claude API, только если явно включён и задан ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import json
import logging
import os
import re

import anthropic

from .schemas import AssistantIn, AssistantOut, OfferOut, Profile, SearchOut
from .service import Service

log = logging.getLogger("assistant")
MODEL = os.getenv("ASSISTANT_MODEL", "claude-opus-5-5")

# ── разбор запроса без модели ────────────────────────────────────

_KIND_WORDS = (("пополнение", r"пополн|робукс|robux|v-?bucks|в-?бакс|донат|валют|gems|кристалл"),
               ("гифт", r"гифт|gift|подар"),
               ("аккаунт", r"аккаунт|акк\b|account|офлайн"),
               ("ключ", r"ключ|\bkey\b|ключик"))
_PLATFORM_WORDS = (("Steam", r"steam|стим"), ("Xbox", r"xbox|иксбокс|хбокс"),
                   ("PlayStation", r"\bps\s?[345]?\b|playstation|плойк|пс\s?[345]"),
                   ("Nintendo", r"nintendo|switch|свитч"), ("Epic", r"\bepic\b|эпик"), ("GOG", r"\bgog\b"))
_STOP = set("""где как какой какая какое самый самая самое самые дешевле дешевую дешёвый дешевый дешево дёшево
всего выгодно выгоднее выгодный выгодное купить куплю покупка хочу надо нужно найди найти подскажи подбери посоветуй
мне для в на и или по до за с со от из это что есть цена цену ценой стоит руб рублей р ₽ не дороже максимум бюджет
лучше лучший лучшее норм нормальный надежный надёжный надежного надёжного продавца продавец игру игра игры""".split())


def parse(text: str) -> dict:
    t = text.lower()
    kind = next((k for k, p in _KIND_WORDS if re.search(p, t)), None)
    platform = next((k for k, p in _PLATFORM_WORDS if re.search(p, t)), None)
    max_price = None
    m = re.search(r"(?:до|не дороже|дешевле|максимум|бюджет|<)\s*(\d+(?:\s\d{3})*)\s*(к|k|тыс)?\b", t)
    if m:
        max_price = float(m.group(1).replace(" ", "")) * (1000 if m.group(2) else 1)
        t = t[:m.start()] + " " + t[m.end():]  # цену из текста убираем, цифры названия (cyberpunk 2077) остаются
    drop = re.compile("|".join(p for _, p in _KIND_WORDS + _PLATFORM_WORDS))
    words = re.sub(r"[^a-z0-9а-яё'’\s-]+", " ", t).replace("’", "'").split()  # апостроф нужен Steam: baldur's gate
    query = " ".join(w for w in words if w not in _STOP and not drop.search(w)).strip()
    if kind == "пополнение" and re.search(r"робукс|robux", t):
        query = "robux"
    return {"query": query, "kind": kind, "platform": platform, "max_price": max_price}


def _rub(x: float) -> str:
    return f"{x:,.0f}".replace(",", " ") + " ₽"


def _offers_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} предложение"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} предложения"
    return f"{n} предложений"


def _rules_answer(p: dict, res: SearchOut, picks: list[OfferOut]) -> str:
    what = res.game.name if res.game else (p["query"] or "это")
    if not res.total_found:
        return (f"По запросу «{p['query']}» в магазинах ничего не нашлось. "
                "Попробуйте написать название игры точнее, например «Elden Ring ключ Steam».")
    if not picks:
        return (f"Нашёл {_offers_word(res.matched)} по «{what}», но ни одно не подходит под условия"
                f"{' — до ' + _rub(p['max_price']) if p['max_price'] else ''}. Попробуйте ослабить фильтры.")
    best = picks[0]
    who = (f"официальный магазин {best.store} (цена пересчитана из $ по курсу ЦБ)" if best.kind == "магазин"
           else f"{best.kind}, {best.platform}, продавец {best.seller} (+{best.reviews_pos} / −{best.reviews_neg})")
    lines = [f"По «{what}» нашёл {_offers_word(res.matched)}. Самое выгодное из надёжных — {_rub(best.price)}: {who}."]
    if len(picks) > 1:
        lines.append("Ещё варианты: " + "; ".join(f"{_rub(o.price)} — {o.seller}" for o in picks[1:3]) + ".")
    if best.kind == "аккаунт":
        lines.append("Учтите: аккаунт — это общий доступ, игра не будет вашей навсегда. Ключ или гифт надёжнее.")
    if res.game and res.game.metacritic:
        lines.append(f"Metacritic: {res.game.metacritic}.")
    return " ".join(lines)


ANY = ["ключ", "гифт", "магазин", "пополнение"]


async def _rules(service: Service, text: str, profile: Profile | None = None) -> AssistantOut:
    p = parse(text)
    if not p["query"]:
        return AssistantOut(answer="Напишите, какую игру или товар ищете — например «ключ Cyberpunk 2077 для Steam до 1500».",
                            offers=[], engine="rules")
    # чего нет в вопросе — берём из профиля пользователя
    if profile:
        p["platform"] = p["platform"] or profile.platform
        p["max_price"] = p["max_price"] or profile.budget
    return await find(service, p, list(profile.kinds) if profile and profile.kinds else ANY, "rules")


async def find(service: Service, p: dict, default_kinds: list[str], engine: str) -> AssistantOut:
    """Поиск под разобранный запрос {query, kind, platform, max_price}; если пусто — ослабляем условия и говорим об этом."""
    kinds = [p["kind"]] if p["kind"] else default_kinds
    plat = [p["platform"]] if p["platform"] else None
    # Если строгих совпадений нет — ослабляем условия по одному и честно говорим об этом
    attempts = [(kinds, plat, p["max_price"], None)]
    if p["kind"] in ("ключ", "гифт"):
        other = "гифт" if p["kind"] == "ключ" else "ключ"
        attempts.append((["ключ", "гифт"], plat, p["max_price"],
                         f"{ {'ключ': 'Ключей', 'гифт': 'Гифтов'}[p['kind']] }{' для ' + p['platform'] if p['platform'] else ''} сейчас нет у надёжных продавцов, "
                         f"но есть {other}."))
    if plat:
        attempts.append((ANY, None, p["max_price"],
                         f"Для {p['platform']} подходящих предложений нет — показываю другие платформы."))
    if p["max_price"]:
        attempts.append((ANY, plat, None,
                         f"В {_rub(p['max_price'])} не уложиться — вот самые дешёвые варианты."))
    res = None
    for kinds_, plat_, price_, note in attempts:
        res = await service.search(p["query"], kinds=kinds_, platforms=plat_, max_price=price_,
                                   trusted_only=True, sort="price", limit=5)
        if res.offers:
            answer = _rules_answer(p, res, res.offers)
            return AssistantOut(answer=f"{note} {answer}" if note else answer, offers=res.offers[:3],
                                game=res.game, engine=engine)
    return AssistantOut(answer=_rules_answer(p, res, []), offers=[], game=res.game, engine=engine)


# ── Claude ──────────────────────────────────────────────────────

SYSTEM = """Ты — ассистент сервиса «Умный Шопинг», агрегатора цен на игры и игровые товары (ключи, гифты, аккаунты, пополнения) у продавцов Plati.market и в официальных магазинах (Steam, GOG, Humble, Fanatical и др.; их цены в $ пересчитаны в рубли, оплата зарубежной картой).
Если в сообщении есть [Профиль пользователя] — используй его бюджет, платформу и типы, когда в вопросе они не указаны.

Как работать:
- Чтобы узнать цены, вызывай инструмент search_offers. Не называй цены, продавцов и ссылки, которых нет в результатах поиска.
- В query передавай только название игры или товара (например «Elden Ring», «robux»), без слов «ключ», «купить», «дешевле».
- Если пользователь не уточнил тип, ищи ключи и гифты: аккаунт — это общий доступ к чужой учётной записи, советуй его только если пользователь сам просит или других вариантов нет, и предупреждай о рисках.
- Рекомендуй 1–3 предложения: цена, тип, платформа, продавец и его отзывы. Объясни выбор в одном-двух предложениях.
- Если запрос неясен (непонятно, какая игра или платформа), задай один уточняющий вопрос вместо поиска.

Отвечай по-русски, коротко, обычным текстом без markdown-разметки — ответ показывается в чате приложения."""

TOOL = {
    "name": "search_offers",
    "description": "Ищет предложения продавцов по игре или игровому товару. Возвращает найденную игру из Steam и до 8 подходящих предложений от надёжных продавцов, отсортированных по цене.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Название игры или товара, например «Elden Ring» или «robux»"},
            "kind": {"type": "string", "enum": ["ключ_или_гифт", "ключ", "гифт", "магазин", "аккаунт", "пополнение", "любой"],
                     "description": "Тип товара; ключ_или_гифт — по умолчанию для игр (включает и официальные магазины); "
                                    "магазин — только официальные магазины (Steam, GOG, Humble…), цена пересчитана из $"},
            "platform": {"type": "string", "enum": ["любая", "Steam", "Xbox", "PlayStation", "Nintendo", "GOG", "Epic"]},
            "max_price": {"type": "number", "description": "Бюджет в рублях; 0 — без ограничения"},
        },
        "required": ["query", "kind", "platform", "max_price"],
        "additionalProperties": False,
    },
}


def has_claude_credentials() -> bool:
    # Claude — только если явно выбран (ASSISTANT_ENGINE=claude) и задан ключ проекта.
    # ANTHROPIC_AUTH_TOKEN / ANTHROPIC_BASE_URL в окружении может выставлять Claude Code для себя — их не берём.
    return os.getenv("ASSISTANT_ENGINE", "").lower() == "claude" and bool(os.getenv("ANTHROPIC_API_KEY"))


def engine_name() -> str:
    """model — своя модель ShopNLU (по умолчанию); rules — регулярные выражения; claude — внешний API (по желанию)."""
    from .nlu import model as nlu
    want = os.getenv("ASSISTANT_ENGINE", "model").lower()
    if want == "claude" and has_claude_credentials():
        return "claude"
    if want != "rules" and nlu.available():
        return "model"
    return "rules"


def _client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"], auth_token=None,
                                    base_url=os.getenv("ASSISTANT_BASE_URL", "https://api.anthropic.com"))


def _compact(o: OfferOut) -> dict:
    return {"id": o.id, "price_rub": o.price, "kind": o.kind, "platform": o.platform, "seller": o.seller,
            "reviews": f"+{o.reviews_pos}/-{o.reviews_neg}", "sold": o.sold, "title": o.title[:90]}


async def _run_tool(service: Service, args: dict, seen: dict[str, OfferOut]) -> tuple[str, SearchOut | None]:
    kind = args.get("kind", "ключ_или_гифт")
    kinds = {"ключ_или_гифт": ["ключ", "гифт", "магазин"], "любой": None}.get(kind, [kind])
    plat = args.get("platform", "любая")
    res = await service.search(str(args.get("query", "")).strip(), kinds=kinds,
                               platforms=None if plat == "любая" else [plat],
                               max_price=args.get("max_price") or None, trusted_only=True, sort="price", limit=8)
    for o in res.offers:
        seen[o.id] = o
    g = res.game
    payload = {
        "game": {"name": g.name, "metacritic": g.metacritic, "steam_review_pct": g.steam_review_pct} if g else None,
        "found_total": res.total_found, "matched_game": res.matched, "kinds_available": res.facets.kinds,
        "offers": [_compact(o) for o in res.offers], "warnings": res.warnings,
    }
    return json.dumps(payload, ensure_ascii=False), res


async def _claude(service: Service, req: AssistantIn) -> AssistantOut:
    client = _client()
    messages: list = []
    for turn in req.history:  # история — только текст; первая реплика должна быть от пользователя
        if not messages and turn.role != "user":
            continue
        messages.append({"role": turn.role, "content": turn.text})
    text = req.message
    if req.profile:  # профиль — условия по умолчанию, если в вопросе их нет
        pr = req.profile
        text += (f"\n\n[Профиль пользователя: бюджет {pr.budget or 'не указан'}, платформа {pr.platform or 'любая'}, "
                 f"подходящие типы {', '.join(pr.kinds) or 'любые'}, регион {pr.region}]")
    messages.append({"role": "user", "content": text})

    seen: dict[str, OfferOut] = {}
    last: SearchOut | None = None
    for _ in range(4):  # обычно хватает одного поиска и ответа
        resp = await client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",            # при отказе классификатора запрос сам повторится на запасной модели
            output_config={"effort": "low"},  # чат: глубокое рассуждение не нужно
            system=SYSTEM,
            tools=[TOOL],
            messages=messages,
        )
        if resp.stop_reason == "refusal":
            return AssistantOut(answer="Не могу помочь с этим запросом. Спросите про игру или игровой товар.",
                                offers=[], engine="claude")
        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})  # целиком, вместе с thinking-блоками
            results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                try:
                    content, last = await _run_tool(service, block.input, seen)
                    results.append({"type": "tool_result", "tool_use_id": block.id, "content": content})
                except Exception as e:  # noqa: BLE001 — ошибку отдаём модели, пусть объяснит пользователю
                    results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                                    "content": f"Поиск не удался: {e}"})
            messages.append({"role": "user", "content": results})
            continue
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        # карточки: предложения, которые модель упомянула по цене или продавцу, иначе топ-3 последнего поиска
        mentioned = [o for o in seen.values() if o.seller and o.seller in text]
        offers = mentioned[:3] or (last.offers[:3] if last else [])
        return AssistantOut(answer=text or "Не получилось сформулировать ответ, попробуйте переформулировать вопрос.",
                            offers=offers, game=last.game if last else None, engine="claude")
    return AssistantOut(answer="Слишком долгий поиск — уточните запрос.", offers=[], engine="claude")


async def answer(service: Service, req: AssistantIn, engine: str | None = None) -> AssistantOut:
    engine = engine or engine_name()
    if engine == "claude":
        try:
            return await _claude(service, req)
        except anthropic.AuthenticationError:
            log.error("ANTHROPIC_API_KEY не подходит — отвечаю своей моделью")
        except anthropic.RateLimitError:
            log.warning("лимит Anthropic API — отвечаю своей моделью")
        except anthropic.APIStatusError as e:
            log.warning("Anthropic API %s — отвечаю своей моделью", e.status_code)
        except anthropic.APIConnectionError:
            log.warning("нет связи с Anthropic API — отвечаю своей моделью")
        from .nlu import model as nlu
        engine = "model" if nlu.available() else "rules"
    if engine == "model":
        from . import smart
        return await smart.answer(service, req)
    return await _rules(service, req.message, req.profile)
