"""Контракт API (P1). По этим моделям FastAPI строит OpenAPI: /docs и /openapi.json."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Kind = Literal["ключ", "гифт", "магазин", "аккаунт", "пополнение", "другое"]
Sort = Literal["price", "trust", "sold"]


class OfferOut(BaseModel):
    id: str = Field(examples=["plati:3412257"], description="«магазин:id» — стабильный ключ предложения")
    store: str = Field(examples=["plati.market"])
    title: str = Field(description="Название как у продавца")
    price: float = Field(examples=[1290.0])
    currency: str = Field(examples=["RUB", "USD"], description="RUB у продавцов, USD у официальных магазинов — без пересчёта")
    url: str = Field(description="Ссылка на покупку")
    seller: str
    seller_rating: float
    sold: int = Field(description="Сколько раз продано")
    reviews_pos: int
    reviews_neg: int
    returns: int
    kind: Kind
    platform: str = Field(examples=["Steam"], description="Steam, Xbox, PlayStation, Nintendo, GOG, Epic, EA, Ubisoft или «?»")
    trusted: bool = Field(description="≥5 положительных отзывов и не больше 10% отрицательных")
    trust_score: float = Field(ge=0, le=1, description="Сглаженная доля положительных отзывов — для сортировки и шкалы надёжности")
    image: str | None = None
    region: str | None = Field(None, description="Регион активации из названия: RU, CIS, GLOBAL, KZ, TR, EU, NO_RU; null — не указан")
    old_price: float | None = Field(None, description="Цена без скидки в той же валюте (официальные магазины)")
    note: str | None = Field(None, description="Пояснение: например, что цена в долларах и нужна зарубежная карта")


class GameOut(BaseModel):
    appid: int = Field(examples=[1245620])
    name: str = Field(examples=["ELDEN RING"])
    genres: list[str]
    image: str | None
    metacritic: int | None
    release: str | None
    steam_review_pct: int | None = Field(None, description="% положительных отзывов Steam (может быть null, если Steam не ответил)")
    steam_reviews: int | None = None


class Facets(BaseModel):
    kinds: dict[str, int] = Field(description="Сколько предложений каждого типа (до фильтрации) — для чипов-фильтров")
    platforms: dict[str, int]


class SearchOut(BaseModel):
    query: str
    game: GameOut | None = Field(description="Игра из Steam, если нашлась; для пополнений и не-Steam товаров — null")
    total_found: int = Field(description="Всего предложений в магазинах по запросу")
    matched: int = Field(description="Из них относятся к этой игре (без DLC и других игр серии)")
    facets: Facets
    offers: list[OfferOut]
    warnings: list[str] = []


class GameCardOut(BaseModel):
    game: GameOut
    offers: list[OfferOut]
    best: dict[str, OfferOut] = Field(description="Самое дешёвое надёжное предложение по каждому типу")


class PricePoint(BaseModel):
    ts: str = Field(description="ISO-время замера")
    price: float


class HistoryOut(BaseModel):
    offer_id: str
    points: list[PricePoint]


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class Profile(BaseModel):
    budget: float | None = Field(None, gt=0, description="Бюджет на игру, ₽")
    platform: str | None = Field(None, examples=["Steam"])
    kinds: list[Kind] = Field(default_factory=list, description="Какие типы товара подходят")
    region: str = Field("RU", description="Где активировать: RU, KZ, TR, EU…")
    genres: list[str] = Field(default_factory=list)


class AssistantIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000, examples=["где дешевле всего купить ключ elden ring в стим до 2000"])
    history: list[ChatTurn] = Field(default_factory=list, max_length=20, description="Предыдущие реплики (необязательно)")
    profile: Profile | None = Field(None, description="Профиль пользователя — условия по умолчанию, если их нет в вопросе")


# ── каталог, витрина, пользователь ──────────────────────────────

class CatalogItem(BaseModel):
    appid: int
    name: str
    image: str | None
    genres: list[str]
    metacritic: int | None
    steam_review_pct: int | None
    best_price: float | None = Field(description="Лучшая цена у надёжных продавцов в рублях (ключ или гифт)")
    best_kind: str | None
    official_price: float | None = Field(description="Минимальная цена в официальных магазинах, в долларах")
    offers: int
    savings_pct: int | None = Field(None, description="Скидка в официальном магазине, % (по данным CheapShark)")
    updated_at: str | None


class StoreOut(BaseModel):
    name: str
    api_type: str
    offers: int


class IdsIn(BaseModel):
    ids: list[str] = Field(max_length=200)


class AuthIn(BaseModel):
    email: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=200)
    name: str | None = Field(None, max_length=100)


class UserOut(BaseModel):
    id: int
    email: str
    name: str | None


class FavoriteItem(BaseModel):
    offer_id: str
    title: str = ""
    price: float = Field(description="Цена в момент добавления")
    appid: int | None = None
    added_at: str = ""
    kind: str | None = Field(None, description="Тип товара — для подбора по истории предпочтений")
    platform: str | None = None
    target_price: float | None = Field(None, gt=0, description="Целевая цена: уведомить, когда цена станет не выше")
    currency: str = Field("RUB", description="Валюта цены предложения")


class MeOut(BaseModel):
    user: UserOut
    profile: Profile
    favorites: list[FavoriteItem]
    token: str | None = Field(None, description="Только при входе/регистрации — для клиентов без cookie")


class NluIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000, examples=["ключ гта 5 для стима до 1.5к"])


class NluOut(BaseModel):
    """Что своя модель ShopNLU поняла из запроса."""
    intent: Literal["buy", "recommend", "review", "compare", "faq", "greet", "other"] = Field(
        description="buy — купить, recommend — подобрать игру, review — отзывы, compare — сравнить цены, faq — вопрос о сервисе")
    confidence: float = Field(ge=0, le=1, description="Уверенность модели в намерении")
    kind: Kind | None = None
    platform: str | None = None
    game: str | None = Field(None, description="Игра или товар, как написал пользователь")
    query: str | None = Field(None, description="Что искать в магазинах (после словаря и сверки с каталогом)")
    max_price: float | None = None
    genre: str | None = Field(None, description="Корень жанра для поиска в жанрах Steam")
    genre_text: str | None = None


class AssistantOut(BaseModel):
    answer: str = Field(description="Ответ ассистента, обычный текст")
    offers: list[OfferOut] = Field(description="Рекомендованные предложения — показать карточками под ответом")
    game: GameOut | None = None
    engine: Literal["model", "rules", "claude"] = Field(
        description="model — своя модель ShopNLU; rules — регулярные выражения; claude — внешний API (если включён)")
    nlu: NluOut | None = Field(None, description="Разбор запроса своей моделью (только engine=model)")


class FeedbackIn(BaseModel):
    helpful: bool = Field(description="Помогла ли рекомендация выбрать")
    where: Literal["search", "game", "assistant", "compare"] = "search"
    offer_id: str | None = Field(None, max_length=200)
    query: str | None = Field(None, max_length=200)


class FeedbackStats(BaseModel):
    total: int
    helpful: int
    helpful_pct: int | None = Field(description="Доля «помогла» — ключевой критерий брифа: не меньше 60%")
    by_place: dict[str, dict[str, int]]


class TelegramPollIn(BaseModel):
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{16,64}$", description="Код из ссылки t.me/<бот>?start=<код>")


class TelegramAuthIn(BaseModel):
    """Что присылает Telegram Login Widget (https://core.telegram.org/widgets/login)."""
    id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str = Field(min_length=64, max_length=64)
