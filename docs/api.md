# API «Умного Шопинга» — контракт

Базовый адрес локально: `http://127.0.0.1:8790`. Интерактивная документация — `/docs`, машинная схема — `/openapi.json` (копия в `docs/openapi.json`, из неё можно сгенерировать типы для фронта: `npx openapi-typescript docs/openapi.json -o src/api.d.ts`).

Все ответы — JSON, цены в рублях. Ошибки: `422` — неверные параметры, `404` — нет игры, `502` — Steam или Plati не ответили (показать «попробуйте ещё раз»).

## Эндпоинты

| Метод | Путь | Для какого экрана |
|---|---|---|
| GET | `/api/search?q=…` | поиск и выдача (A1) |
| GET | `/api/games/{appid}` | карточка игры (A2) |
| GET | `/api/offers/{offer_id}/history` | график цены (A2) |
| POST | `/api/assistant` | чат ИИ-ассистента (A3) |
| GET | `/api/health` | проверка, что сервер жив; `assistant`: `claude` или `rules` |

### GET /api/search

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `q` | строка, 2–100 | — | название игры или товара |
| `kind` | строка, можно несколько | все | `ключ`, `гифт`, `аккаунт`, `пополнение`, `другое` |
| `platform` | строка, можно несколько | все | `Steam`, `Xbox`, `PlayStation`, `Nintendo`, `GOG`, `Epic`, `EA`, `Ubisoft`, `?` |
| `max_price` | число | — | максимум, ₽ |
| `trusted_only` | bool | `false` | только надёжные продавцы |
| `sort` | `price` / `trust` / `sold` | `price` | `price` — надёжные дешёвые сверху |
| `limit` | 1–200 | 50 | |

По ТЗ фронт по умолчанию шлёт `kind=ключ&kind=гифт`. `facets` считаются до фильтров — по ним рисуются счётчики на чипах.

```json
{
  "query": "elden ring",
  "game": {"appid": 1245620, "name": "ELDEN RING", "genres": ["Ролевые игры"], "image": "https://…/header.jpg",
           "metacritic": 94, "release": "25 фев. 2022", "steam_review_pct": null, "steam_reviews": null},
  "total_found": 100,
  "matched": 51,
  "facets": {"kinds": {"аккаунт": 31, "гифт": 10, "ключ": 4}, "platforms": {"Steam": 30, "Xbox": 9}},
  "offers": [{
    "id": "plati:4823791", "store": "plati.market", "title": "ELDEN RING STEAM GIFT 🚀АВТОДОСТАВКА💳0%",
    "price": 2716.0, "currency": "RUB", "url": "https://plati.market/itm/…",
    "seller": "…", "seller_rating": 812.0, "sold": 431, "reviews_pos": 9, "reviews_neg": 0, "returns": 0,
    "kind": "гифт", "platform": "Steam", "trusted": true, "trust_score": 0.909, "image": null
  }],
  "warnings": []
}
```

- `matched` — сколько предложений относится именно к этой игре: без DLC и без других игр серии (Nightreign при поиске Elden Ring).
- `game: null` — товар не из Steam (робуксы, пополнения): карточку игры не показывать.
- `steam_review_pct` бывает `null` — Steam отдаёт отзывы не из всех регионов, блок просто скрываем.
- `warnings` — показать мелким текстом над выдачей.

### GET /api/games/{appid}

`{ game, offers[], best }`, где `best` — самое дешёвое надёжное предложение каждого типа: `{"ключ": Offer, "гифт": Offer, …}`. Удобно для шапки карточки («от 2 716 ₽»).

### GET /api/offers/{offer_id}/history

`{"offer_id": "plati:4823791", "points": [{"ts": "2026-11-08T14:36:51+00:00", "price": 2716.0}]}`.
Точка пишется, когда цена меняется. Пока данные копятся с первых запросов; после запуска загрузчика Сени (S2) история будет ежедневной.

### POST /api/assistant

Запрос: `{"message": "где дешевле ключ cyberpunk 2077 для стим", "history": [{"role": "user", "text": "…"}, {"role": "assistant", "text": "…"}]}` (`history` необязателен, до 20 реплик).

Ответ:
```json
{
  "answer": "Ключей для Steam сейчас нет у надёжных продавцов, но есть гифт. …",
  "offers": [Offer, Offer, Offer],
  "game": Game,
  "engine": "rules"
}
```
`answer` — обычный текст без разметки. `offers` — 0–3 карточки под сообщением. `engine` можно не показывать.

## Модель данных (для БД, S1)

Ответы API уже соответствуют этим таблицам — когда БД будет готова, сервис переключится на неё без изменения контракта.

| Таблица | Поля |
|---|---|
| `product` | `id`, `steam_appid` (уникальный, ключ склейки), `title`, `genres` (text[]), `image`, `metacritic`, `steam_review_pct`, `release`, `updated_at` |
| `store` | `id`, `name` (`plati.market`, `ggsel`), `url`, `api_type` |
| `offer` | `id`, `product_id` (nullable — пополнения без игры), `store_id`, `external_id`, `title`, `price`, `currency`, `url`, `seller`, `seller_rating`, `sold`, `reviews_pos`, `reviews_neg`, `returns`, `kind`, `platform`, `trusted`, `trust_score`, `section_id`, `updated_at`; уникальность `(store_id, external_id)` |
| `price_history` | `offer_id`, `price`, `fetched_at`; индекс `(offer_id, fetched_at)` |

Тип, платформа, DLC, склейка и надёжность — функции `offer_kind`, `offer_platform`, `is_dlc`, `matches`, `trust` в `app/sources.py`, их стоит импортировать в загрузчик, а не переписывать.
