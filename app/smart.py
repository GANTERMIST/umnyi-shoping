"""Помощник на своей модели: ShopNLU разбирает запрос → поиск/каталог → ответ по шаблонам из реальных данных.

Внешний ИИ не нужен: все цифры в ответе берутся из поиска и базы, модель решает только,
ЧТО хочет пользователь (купить, подобрать игру, узнать отзывы, сравнить цены, спросить «что такое гифт»…).
"""
from __future__ import annotations

import re

from .assistant import ANY, _rub, find
from .nlu import model as nlu
from .nlu.model import Frame
from .schemas import AssistantIn, AssistantOut, CatalogItem, NluOut, OfferOut, Profile
from .service import Service, offer_out

GOOD = ["ключ", "гифт", "магазин"]
KIND_NAME = {"ключ": "ключ", "гифт": "гифт", "магазин": "официальный магазин", "аккаунт": "аккаунт",
             "пополнение": "пополнение", "другое": "товар"}

EXAMPLES = "«ключ Elden Ring для Steam до 2000», «посоветуй рпг до 1000», «стоит ли брать Hades», «что такое гифт»"
HELP = ("Я помощник «Умного Шопинга» — своя небольшая модель, обученная на запросах покупателей игр. Умею:\n"
        "• найти, где дешевле купить игру, ключ, гифт или пополнение — с учётом бюджета, платформы и профиля;\n"
        "• подобрать игру из каталога по жанру и бюджету или найти, что сейчас выгодно;\n"
        "• рассказать про отзывы и оценки игры;\n"
        "• сравнить цену у продавцов и в официальных магазинах;\n"
        "• объяснить, чем ключ отличается от гифта, что такое регион и как не нарваться на обман.\n"
        f"Например: {EXAMPLES}.")

FAQ = {
    "key_vs_gift": "Ключ — код, который вы сами вводите в Steam (или другом сервисе), игра навсегда ваша. Гифт — продавец дарит "
                   "игру на ваш аккаунт через Steam (нужно указать ссылку на профиль или добавить его в друзья), игра тоже "
                   "ваша навсегда. Гифт обычно чуть дороже и жёстче привязан к региону; ключ можно передать другу.",
    "ключ": "Ключ — код активации. В Steam: «Игры» → «Активировать в Steam» → ввести код; на Xbox и PlayStation — в магазине "
            "приставки «Использовать код». Игра остаётся у вас навсегда. Проверьте регион ключа: «RU/СНГ/Global» подходит "
            "для российского аккаунта, «не для РФ» — нет. Если ключ не подошёл — пишите продавцу через Plati, это гарантийный случай.",
    "гифт": "Гифт — подарок через Steam: продавец отправляет игру на ваш аккаунт, вы принимаете её в уведомлениях Steam, и она "
            "навсегда ваша. «Автодоставка» — бот отправит сам за несколько минут. Регион вашего аккаунта должен совпадать с "
            "регионом гифта — в таблице это видно в колонке «Регион».",
    "аккаунт": "Аккаунт — вам дают логин и пароль от чужой учётной записи с игрой. Поэтому так дёшево: игра не ваша, "
               "владелец может забрать доступ, офлайн-аккаунт работает только без интернета, «П2/П3» на PlayStation — "
               "общий доступ. Забанить за это могут именно этот аккаунт. Если хотите игру навсегда — берите ключ или гифт.",
    "пополнение": "Пополнение — продавец зачисляет валюту (робуксы, V-Bucks, кристаллы) или деньги на кошелёк по вашему "
                  "логину/ID. Обычно занимает от пары минут до часа. Выбирайте продавцов с отметкой «Надёжный» и "
                  "никогда не отдавайте пароль, если хватает логина или ID.",
    "магазин": "Официальный магазин — покупка напрямую в Steam, GOG, Humble, Fanatical и др. Цены мы берём через CheapShark "
               "в долларах и пересчитываем по курсу ЦБ, поэтому они ориентировочные; оплатить там из России можно только "
               "зарубежной картой. Зато это без посредников и без риска с регионом.",
    "region": "Регион — где можно активировать товар. RU и СНГ подходят для российского аккаунта, Global — для любого, "
              "«не для РФ», TR, EU, KZ — не для российского. Мы определяем регион по описанию продавца и сравниваем с регионом "
              "из вашего профиля: зелёный — подходит, красный — нет, жёлтый — продавец не указал, уточните перед покупкой.",
    "safety": "Деньги на Plati.market защищены: если товар не подошёл, откройте спор в заказе — у продавца есть время "
              "исправить, иначе деньги вернут. Чтобы не нарваться: смотрите на «Надёжность» (≥5 положительных отзывов и не больше "
              "10% отрицательных), число продаж и регион, не платите продавцу напрямую мимо площадки.",
    "trust": "Надёжность — это доля положительных отзывов продавца с поправкой на малое число отзывов: (плюсы+1)/(все+2). "
             "«Надёжный» — минимум 5 положительных и не больше 10% отрицательных. Официальные магазины всегда надёжны.",
    "data": "Цены продавцов — из открытого API Plati.market, официальных магазинов — из CheapShark, сведения об играх и "
            "отзывы — из Steam. Загрузчик обновляет базу по популярным играм, а при поиске цены берутся заново в реальном времени.",
    "features": "Нажмите ♥ у предложения — цена запомнится, и если она изменится, в меню «Избранное» появится значок, "
                "а в списке будет видно, на сколько подешевело. Галочка «Сравнить» добавляет до 4 предложений в сравнение.",
    "general": "Сервис ищет игру у продавцов Plati.market и в официальных магазинах, отсеивает DLC и чужие игры серии, "
               "показывает надёжность продавца и регион и подбирает лучшее под ваш профиль. " + f"Попробуйте: {EXAMPLES}.",
}


def _faq_topic(text: str, kind: str | None) -> str:
    t = text.lower()
    if re.search(r"ключ", t) and re.search(r"гифт|gift", t):
        return "key_vs_gift"
    if re.search(r"регион|\bru\b|снг|global|глобал|не для рф", t):
        return "region"
    if re.search(r"надежн|надёжн|процент", t):
        return "trust"
    if kind in ("аккаунт", "пополнение"):
        return kind
    if re.search(r"вернут|возврат|обман|гарант|кинул|мошен|безопасн", t):
        return "safety"
    if re.search(r"откуда|обновля|данные|цены бер|plati|плати|cheapshark", t) and kind != "магазин":
        return "data"
    if re.search(r"избранн|уведомл|изменилась|сравнени", t):
        return "features"
    return kind if kind in FAQ else "general"


def _verdict(pct: int | None) -> str:
    if pct is None:
        return ""
    if pct >= 95:
        return "крайне положительные"
    if pct >= 80:
        return "очень положительные"
    if pct >= 70:
        return "в основном положительные"
    if pct >= 40:
        return "смешанные"
    return "в основном отрицательные"


async def _buy(service: Service, f: Frame, profile: Profile | None) -> AssistantOut:
    p = {"query": f.query, "kind": f.kind,
         "platform": f.platform or (profile.platform if profile else None),
         "max_price": f.max_price or (profile.budget if profile else None)}
    return await find(service, p, list(profile.kinds) if profile and profile.kinds else ANY, "model")


async def _review(service: Service, f: Frame, profile: Profile | None) -> AssistantOut:
    res = await service.search(f.query, kinds=GOOD, trusted_only=True, sort="price", limit=3)
    g = res.game
    if not g:
        tail = f" У продавцов нашлось {res.matched} предложений — спросите «где купить {f.game}»." if res.matched else ""
        return AssistantOut(answer=f"Не нашёл «{f.game}» в Steam, поэтому про отзывы сказать не могу.{tail}",
                            offers=res.offers[:3], engine="model")
    parts = [f"{g.name} ({', '.join(g.genres[:3]) or 'жанр не указан'})."]
    if g.steam_review_pct is not None:
        parts.append(f"Отзывы в Steam {_verdict(g.steam_review_pct)}: {g.steam_review_pct}% положительных"
                     f"{f' из {g.steam_reviews:,}'.replace(',', ' ') if g.steam_reviews else ''}.")
    if g.metacritic:
        word = "отлично" if g.metacritic >= 85 else "хорошо" if g.metacritic >= 75 else "средне" if g.metacritic >= 60 else "слабо"
        parts.append(f"Metacritic — {g.metacritic} ({word}).")
    score = g.steam_review_pct if g.steam_review_pct is not None else g.metacritic
    if score is None:
        parts.append("Оценок пока нет — посмотрите обзоры перед покупкой.")
    elif score >= 80:
        parts.append("Игроки довольны — брать можно.")
    elif score >= 60:
        parts.append("В целом неплохо, но есть недовольные — гляньте свежие отзывы.")
    else:
        parts.append("Многие недовольны — подумайте, прежде чем покупать.")
    if res.offers:
        o = res.offers[0]
        parts.append(f"Купить сейчас можно от {_rub(o.price)} ({KIND_NAME[o.kind]}, {o.seller}).")
    return AssistantOut(answer=" ".join(parts), offers=res.offers[:3], game=g, engine="model")


async def _compare(service: Service, f: Frame, profile: Profile | None) -> AssistantOut:
    res = await service.search(f.query, kinds=GOOD, trusted_only=True, sort="price", limit=200)
    name = res.game.name if res.game else f.game
    sellers = [o for o in res.offers if o.kind in ("ключ", "гифт")]
    official = [o for o in res.offers if o.kind == "магазин"]
    if not sellers and not official:
        return AssistantOut(answer=f"По «{name}» не нашёл предложений от надёжных продавцов и официальных магазинов.",
                            offers=[], game=res.game, engine="model")
    parts = []
    if sellers:
        s = sellers[0]
        parts.append(f"У продавцов {name} от {_rub(s.price)} ({s.kind}, {s.platform}, {s.seller}).")
    if official:
        o = official[0]
        parts.append(f"В официальных магазинах — от {_rub(o.price)} ({o.store}; всего магазинов: {len(official)}).")
    else:
        parts.append("Официальных цен нет: CheapShark не знает эту игру или она бесплатная.")
    if sellers and official:
        diff = official[0].price - sellers[0].price
        if diff > 0:
            parts.append(f"У продавцов дешевле на {_rub(diff)} ({round(100 * diff / official[0].price)}%).")
        else:
            parts.append(f"Официально даже дешевле на {_rub(-diff)} — берите в магазине.")
        parts.append("Помните: у продавцов важен регион ключа или гифта, а официальная цена в $ — платить нужно зарубежной картой.")
    picks = sellers[:2] + official[:1]
    return AssistantOut(answer=" ".join(parts), offers=picks, game=res.game, engine="model")


def _has_genre(item: CatalogItem, stem: str) -> bool:
    return any(stem in g.lower() for g in item.genres)


async def _recommend(service: Service, f: Frame, profile: Profile | None) -> AssistantOut:
    items = [i for i in service.catalog(500) if i.best_price]
    if not items:
        return AssistantOut(answer="Каталог пока пуст — запустите загрузчик цен (python -m app.loader) или спросите про "
                                   "конкретную игру.", offers=[], engine="model")
    budget = f.max_price or (profile.budget if profile else None)
    conds, note = [], None
    pool = items
    like = None
    if f.game:  # «что-то похожее на Hades» — по жанрам этой игры
        row = service.db.find_product(f.query or f.game)
        if row:
            like = service.db.game(row)
            base = set(like.genres) - {"Инди", "Бесплатные"} or set(like.genres)
            pool = sorted([i for i in items if i.appid != like.appid and base & set(i.genres)],
                          key=lambda i: -len(base & set(i.genres)))
            conds.append(f"похоже на {like.name}")
        else:
            note = f"Игры «{f.game}» нет в каталоге — подбираю из популярных."
    if f.genre:
        g_pool = [i for i in pool if _has_genre(i, f.genre)]
        if g_pool:
            pool = g_pool
            conds.append(f"жанр «{f.genre_text}»")
        else:
            note = f"В каталоге нет игр жанра «{f.genre_text}» — показываю другие."
    if budget:
        b_pool = [i for i in pool if i.best_price <= budget]
        if b_pool:
            pool = b_pool
            conds.append(f"до {_rub(budget)}")
        else:
            note = f"До {_rub(budget)} подходящих нет — вот самые близкие по цене."
            pool = sorted(pool, key=lambda i: i.best_price)
    if not (f.genre or like or budget):  # «что сейчас выгодно» — по скидке к официальной цене
        pool = sorted(pool, key=lambda i: (-(i.savings_pct or 0), -(i.steam_review_pct or 0)))
        conds.append("самые большие скидки к официальной цене")
    elif not like:
        pool = sorted(pool, key=lambda i: (-(i.steam_review_pct or 60) - 0.3 * (i.savings_pct or 0)))
    top = pool[:3]
    lines = [(note + " ") if note else ""]
    lines[0] += ("Подобрал" + (f" ({', '.join(conds)})" if conds else "") + ":")
    offers: list[OfferOut] = []
    for n, i in enumerate(top, 1):
        bits = [f"от {_rub(i.best_price)}" + (f" ({KIND_NAME.get(i.best_kind, i.best_kind)})" if i.best_kind else "")]
        if i.steam_review_pct is not None:
            bits.append(f"{i.steam_review_pct}% положительных отзывов")
        if i.savings_pct:
            bits.append(f"на {i.savings_pct}% дешевле официальной цены")
        lines.append(f"{n}. {i.name} — {', '.join(bits)}.")
        o = service.db.best_offer(i.appid)
        if o:
            offers.append(offer_out(o))
    lines.append("Нажмите на карточку, чтобы купить, или спросите «стоит ли брать …» про любую из них.")
    return AssistantOut(answer="\n".join(lines), offers=offers, engine="model")


async def _faq(service: Service, f: Frame, text: str) -> AssistantOut:
    return AssistantOut(answer=FAQ[_faq_topic(text, f.kind)], offers=[], engine="model")


def _greet(text: str) -> AssistantOut:
    t = text.lower()
    if re.search(r"спасиб|благодар|спс|пасиб", t):
        ans = "Пожалуйста! Если нужно ещё что-то найти — пишите."
    elif re.search(r"пока|до свидан", t):
        ans = "До встречи! Цены в избранном будут отслеживаться и без меня."
    elif re.search(r"^(ок|ясно|понял|понятно|хорошо|круто|отлично|супер|класс)\b", t):
        ans = f"Отлично. Что ищем? Например: {EXAMPLES}."
    else:
        ans = HELP
    return AssistantOut(answer=ans, offers=[], engine="model")


OTHER = ("Я помогаю только с играми и игровыми товарами: ключи, гифты, пополнения, подбор игры, отзывы и сравнение цен. "
         f"Спросите, например: {EXAMPLES}.")


async def answer(service: Service, req: AssistantIn) -> AssistantOut:
    m = nlu.get()
    f = m.parse(req.message)
    from_history = False
    if f.intent in ("buy", "review", "compare") and not f.game:  # «а для xbox?» — игра из прошлых реплик
        for turn in reversed(req.history):
            if turn.role == "user":
                prev = m.parse(turn.text)
                if prev.game:
                    f.game, from_history = prev.game, True
                    break
    if f.game:
        f.query = nlu.resolve(f.game, service.db.titles())
    profile = req.profile
    if f.intent == "buy" and not f.game:
        f.intent = "recommend" if (f.max_price or f.genre) else f.intent
    if f.confidence < 0.45 and not f.game:
        out = AssistantOut(answer=f"Не совсем понял. Напишите название игры или что хотите подобрать — например {EXAMPLES}.",
                           offers=[], engine="model")
    elif f.intent == "buy":
        out = (await _buy(service, f, profile) if f.game else
               AssistantOut(answer=f"Какую игру или товар ищете? Например: {EXAMPLES}.", offers=[], engine="model"))
    elif f.intent in ("review", "compare"):
        if not f.game:
            out = AssistantOut(answer="Про какую игру? Напишите название, например «стоит ли брать Hades».", offers=[], engine="model")
        else:
            out = await (_review if f.intent == "review" else _compare)(service, f, profile)
    elif f.intent == "recommend":
        out = await _recommend(service, f, profile)
    elif f.intent == "faq":
        out = await _faq(service, f, req.message)
    elif f.intent == "greet":
        out = _greet(req.message)
    else:
        out = AssistantOut(answer=OTHER, offers=[], engine="model")
    if from_history and out.answer:
        out.answer = f"(про {f.game}) {out.answer}"
    out.nlu = NluOut(**f.as_dict())
    return out
