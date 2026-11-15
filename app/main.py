"""API «Умного Шопинга» + раздача собранного фронтенда.

Запуск:  python -m uvicorn app.main:app --port 8790     (из папки umnyi-shoping)
Сайт: http://127.0.0.1:8790/     Документация API: http://127.0.0.1:8790/docs
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Cookie, FastAPI, Header, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from . import assistant, auth
from .schemas import (AssistantIn, AssistantOut, AuthIn, CatalogItem, FavoriteItem, GameCardOut, HistoryOut, IdsIn,
                      FeedbackIn, FeedbackStats, MeOut, NluIn, NluOut, OfferOut, Profile, SearchOut, Sort, StoreOut, UserOut)
from .service import Service
from .sources import SourceError, Sources

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "frontend" / "dist"
load_dotenv(ROOT / ".env")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    sources = Sources()
    app.state.service = Service(sources, Path(os.getenv("DATA_DIR", ROOT / "data")))
    yield
    await sources.aclose()
    app.state.service.db.db.close()


app = FastAPI(
    title="Умный Шопинг API",
    version="1.1.0",
    description="Агрегатор цен на игры: Plati.market + официальные магазины (через CheapShark) + Steam как справочник; "
                "история цен, избранное, профиль и ИИ-ассистент.",
    lifespan=lifespan,
)
_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT"], allow_headers=["*"])


def svc() -> Service:
    return app.state.service


def _token(cookie: str | None, authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return cookie


def _uid(cookie: str | None, authorization: str | None) -> int:
    uid = auth.user_from_token(svc().db, _token(cookie, authorization))
    if not uid:
        raise HTTPException(401, "Нужно войти")
    return uid


def _me(uid: int, token: str | None = None) -> MeOut:
    u = svc().db.user_by_id(uid)
    profile, favorites = svc().db.user_data(uid)
    return MeOut(user=UserOut(id=u["id"], email=u["email"], name=u["name"]), profile=Profile(**profile),
                 favorites=[FavoriteItem(**f) for f in favorites], token=token)


def _session_response(uid: int) -> JSONResponse:
    token = auth.new_session(svc().db, uid)
    resp = JSONResponse(_me(uid, token).model_dump())
    resp.set_cookie(auth.COOKIE, token, max_age=auth.SESSION_DAYS * 86400, httponly=True, samesite="lax",
                    secure=os.getenv("COOKIE_SECURE") == "1")
    return resp


SessionCookie = Annotated[str | None, Cookie(alias=auth.COOKIE, include_in_schema=False)]
AuthHeader = Annotated[str | None, Header(include_in_schema=False)]


# ── служебное ───────────────────────────────────────────────────

@app.get("/api/health", tags=["служебное"])
async def health() -> dict:
    return {"ok": True, "assistant": assistant.engine_name()}


# ── поиск и игры ────────────────────────────────────────────────

@app.get("/api/search", response_model=SearchOut, tags=["поиск"], summary="Поиск предложений по игре или товару")
async def search(
    q: Annotated[str, Query(min_length=2, max_length=100, description="Название игры или товара", examples=["elden ring"])],
    kind: Annotated[list[str] | None, Query(description="Фильтр по типу, можно несколько: kind=ключ&kind=гифт&kind=магазин")] = None,
    platform: Annotated[list[str] | None, Query(description="Фильтр по платформе, можно несколько")] = None,
    store: Annotated[list[str] | None, Query(description="Фильтр по магазину: plati.market, Steam, GOG…")] = None,
    max_price: Annotated[float | None, Query(gt=0, description="Максимальная цена, ₽")] = None,
    trusted_only: Annotated[bool, Query(description="Только надёжные продавцы")] = False,
    sort: Annotated[Sort, Query(description="price — дешевле сверху (надёжные первыми), trust — по надёжности, sold — по продажам")] = "price",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> SearchOut:
    try:
        return await svc().search(q, kind, platform, max_price, trusted_only, sort, limit, stores=store)
    except SourceError as e:
        raise HTTPException(502, f"Источник данных не ответил: {e}") from e


@app.get("/api/games/{appid}", response_model=GameCardOut, tags=["игры"],
         summary="Карточка игры: данные Steam, все предложения и лучшее по каждому типу")
async def game(appid: int) -> GameCardOut:
    try:
        card = await svc().game_card(appid)
    except SourceError as e:
        raise HTTPException(502, f"Источник данных не ответил: {e}") from e
    if not card:
        raise HTTPException(404, "Игра не найдена в Steam")
    return card


@app.get("/api/offers/{offer_id}/history", response_model=HistoryOut, tags=["игры"],
         summary="История цены предложения (для графика)")
async def history(offer_id: str) -> HistoryOut:
    return svc().price_history(offer_id)


@app.post("/api/offers/current", response_model=list[OfferOut], tags=["игры"],
          summary="Текущие цены предложений из базы (для избранного и уведомлений об изменении цены)")
async def current(body: IdsIn) -> list[OfferOut]:
    return svc().current(body.ids)


@app.get("/api/catalog", response_model=list[CatalogItem], tags=["каталог"], summary="Игры в базе с лучшей ценой")
async def catalog(limit: Annotated[int, Query(ge=1, le=500)] = 60) -> list[CatalogItem]:
    return svc().catalog(limit)


@app.get("/api/deals", response_model=list[CatalogItem], tags=["каталог"],
         summary="«Выгодно сегодня»: где цена продавцов заметно ниже официальной")
async def deals(limit: Annotated[int, Query(ge=1, le=50)] = 12) -> list[CatalogItem]:
    return svc().deals(limit)


@app.get("/api/games/{appid}/similar", response_model=list[CatalogItem], tags=["игры"],
         summary="Похожие игры из каталога: общие жанры, близкая цена")
async def similar(appid: int, limit: Annotated[int, Query(ge=1, le=20)] = 6) -> list[CatalogItem]:
    return [CatalogItem(**c) for c in svc().db.similar(appid, limit)]


@app.post("/api/feedback", tags=["оценка"], summary="«Помогла ли рекомендация?» — ответ пользователя")
async def feedback(body: FeedbackIn) -> dict:
    svc().db.add_feedback(body.helpful, body.where, body.offer_id, body.query)
    return {"ok": True}


@app.get("/api/feedback/stats", response_model=FeedbackStats, tags=["оценка"],
         summary="Сколько пользователей отметили, что рекомендация помогла (критерий брифа ≥ 60%)")
async def feedback_stats() -> FeedbackStats:
    return FeedbackStats(**svc().db.feedback_stats())


@app.get("/api/stores", response_model=list[StoreOut], tags=["каталог"], summary="Подключённые площадки")
async def stores() -> list[StoreOut]:
    return [StoreOut(**s) for s in svc().db.stores()]


# ── ассистент ───────────────────────────────────────────────────

@app.post("/api/assistant", response_model=AssistantOut, tags=["ассистент"],
          summary="ИИ-ассистент: вопрос пользователя → ответ и рекомендованные предложения")
async def ask(body: AssistantIn) -> AssistantOut:
    try:
        return await assistant.answer(svc(), body)
    except SourceError as e:
        raise HTTPException(502, f"Источник данных не ответил: {e}") from e


@app.post("/api/nlu", response_model=NluOut, tags=["ассистент"],
          summary="Разбор запроса своей моделью ShopNLU (намерение, игра, тип, платформа, бюджет, жанр)")
async def nlu_parse(body: NluIn) -> NluOut:
    from .nlu import model as nlu
    if not nlu.available():
        raise HTTPException(503, "Модель не обучена: python -m app.nlu.train")
    f = nlu.get().parse(body.text)
    if f.game:
        f.query = nlu.resolve(f.game, svc().db.titles())
    return NluOut(**f.as_dict())


# ── пользователь ────────────────────────────────────────────────

def _auth_call(fn, *args):
    try:
        return fn(*args)
    except auth.AuthError as e:
        raise HTTPException(e.status, e.message) from e


@app.post("/api/auth/register", response_model=MeOut, tags=["пользователь"], summary="Регистрация (сразу входит)")
async def register(body: AuthIn) -> JSONResponse:
    uid = _auth_call(auth.register, svc().db, body.email, body.password, body.name)
    return _session_response(uid)


@app.post("/api/auth/login", response_model=MeOut, tags=["пользователь"], summary="Вход")
async def login(body: AuthIn) -> JSONResponse:
    uid = _auth_call(auth.login, svc().db, body.email, body.password)
    return _session_response(uid)


@app.post("/api/auth/logout", tags=["пользователь"], summary="Выход")
async def logout(response: Response, us_session: SessionCookie = None, authorization: AuthHeader = None) -> dict:
    auth.logout(svc().db, _token(us_session, authorization))
    response.delete_cookie(auth.COOKIE)
    return {"ok": True}


@app.get("/api/me", response_model=MeOut, tags=["пользователь"], summary="Профиль и избранное")
async def me(us_session: SessionCookie = None, authorization: AuthHeader = None) -> MeOut:
    return _me(_uid(us_session, authorization))


@app.put("/api/me/profile", response_model=MeOut, tags=["пользователь"], summary="Сохранить профиль")
async def put_profile(body: Profile, us_session: SessionCookie = None, authorization: AuthHeader = None) -> MeOut:
    uid = _uid(us_session, authorization)
    svc().db.put_user_data(uid, profile=body.model_dump())
    return _me(uid)


@app.put("/api/me/favorites", response_model=MeOut, tags=["пользователь"], summary="Сохранить избранное")
async def put_favorites(body: list[FavoriteItem], us_session: SessionCookie = None,
                        authorization: AuthHeader = None) -> MeOut:
    uid = _uid(us_session, authorization)
    if len(body) > 200:
        raise HTTPException(422, "Не больше 200 товаров в избранном")
    svc().db.put_user_data(uid, favorites=[f.model_dump() for f in body])
    return _me(uid)


# ── фронтенд (frontend/dist после npm run build) ────────────────

@app.get("/{path:path}", include_in_schema=False)
async def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "Нет такого метода API")
    f = (DIST / path).resolve()
    if path and f.is_file() and DIST.resolve() in f.parents:
        return FileResponse(f)
    index = DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    return JSONResponse({"message": "Фронтенд не собран: cd frontend && npm install && npm run build. API: /docs"})
