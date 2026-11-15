"""Офлайн-тесты API: Steam и Plati подменены через httpx.MockTransport."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["ASSISTANT_ENGINE"] = "rules"  # тесты не ходят в Anthropic API

from app import assistant, sources as src  # noqa: E402
from app.schemas import AssistantIn  # noqa: E402
from app.service import Service  # noqa: E402


def plati_item(i, name, price, pos=100, neg=1, ret=0):
    return {"id": i, "name": name, "price_rur": price, "url": f"https://plati.market/itm/{i}",
            "seller_name": f"seller{i}", "seller_rating": 500, "numsold": 1000 + i,
            "count_positiveresponses": pos, "count_negativeresponses": neg, "count_returns": ret}


PLATI = [
    plati_item(1, "ELDEN RING Steam Key RU+CIS", 1890),
    plati_item(2, "ELDEN RING (Steam Gift) Россия", 2100),
    plati_item(3, "ELDEN RING NIGHTREIGN ключ Steam", 990),          # другая игра серии
    plati_item(4, "ELDEN RING - Tarnished Edition DLC Pack", 300),  # DLC
    plati_item(5, "ELDEN RING офлайн аккаунт Steam", 150),
    plati_item(6, "ELDEN RING ключ Steam дешево", 1500, pos=2, neg=3),  # ненадёжный продавец
    plati_item(7, "ELDEN RING Xbox One / Series key", 1700),
    plati_item(8, "Roblox 800 Robux пополнение", 650),
]
STEAM_SEARCH = {"items": [{"id": 1245620, "name": "ELDEN RING"}, {"id": 2622380, "name": "ELDEN RING NIGHTREIGN"}]}
STEAM_APP = {"1245620": {"success": True, "data": {"name": "ELDEN RING", "genres": [{"description": "Ролевые игры"}],
                                                   "header_image": "https://x/h.jpg", "metacritic": {"score": 94},
                                                   "release_date": {"date": "25 фев. 2022"}}}}


CHEAP_DEALS: list = []  # по умолчанию официальные магазины пусты — тесты Plati не меняются
STATE = {"plati_down": False}


def handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if "cheapshark.com/api/1.0/deals" in url:
        return httpx.Response(200, json=CHEAP_DEALS)
    if "cheapshark.com/api/1.0/stores" in url:
        return httpx.Response(200, json=[{"storeID": "1", "storeName": "Steam", "isActive": 1},
                                         {"storeID": "7", "storeName": "GOG", "isActive": 1}])
    if "cbr-xml-daily" in url:
        return httpx.Response(200, json={"Valute": {"USD": {"Value": 80.0}}})
    if "plati.io" in url and STATE["plati_down"]:
        return httpx.Response(503)
    if "plati.io" in url:
        q = request.url.params["query"].lower()
        items = [it for it in PLATI if all(w in it["name"].lower() for w in q.split())]
        return httpx.Response(200, json={"items": items, "Totalpages": 1})
    if "storesearch" in url:
        term = request.url.params["term"].lower()
        return httpx.Response(200, json=STEAM_SEARCH if "elden" in term else {"items": []})
    if "appdetails" in url:
        return httpx.Response(200, json=STEAM_APP)
    if "appreviews" in url:
        return httpx.Response(200, json={"query_summary": {"total_reviews": 1000, "total_positive": 930}})
    return httpx.Response(404)


class Base(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sources = src.Sources(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        self.svc = Service(self.sources, Path(self.tmp.name))

    async def asyncTearDown(self):
        await self.sources.aclose()
        self.svc.history.db.close()
        self.tmp.cleanup()


class NormalizeTest(unittest.TestCase):
    def test_kind_real_titles(self):  # реальные названия с Plati
        self.assertEqual(src.offer_kind("ELDEN RING Deluxe + NEW DLC  (Steam) Оффлайн"), "аккаунт")
        self.assertEqual(src.offer_kind("Elden Ring (PS4/PS5/RUS) Аренда 7 дней"), "аккаунт")
        self.assertEqual(src.offer_kind("ELDEN RING PS4/PS5 | П2/П3"), "аккаунт")
        self.assertEqual(src.offer_kind("ELDEN RING +ВЫБОР STEAM•RU ⚡️АВТОДОСТАВКА 💳0%"), "гифт")
        self.assertEqual(src.offer_kind("Hogwarts Legacy XBOX SERIES X|S / ПК Ключ 🔑"), "ключ")
        self.assertEqual(src.offer_kind("⭐️TOP⭐️ ELDEN RING - STEAM (GLOBAL) +$БОНУС", 22764), "аккаунт")
        self.assertEqual(src.offer_kind("🔥 ELDEN RING | Steam РУ+UA+KZ+СНГ🔥", 49950), "другое")
        self.assertEqual(src.offer_kind("ROBUX ПОПОЛНЕНИЕ АККАУНТА", 22764), "пополнение")

    def test_kind(self):
        self.assertEqual(src.offer_kind("ELDEN RING Steam Key"), "ключ")
        self.assertEqual(src.offer_kind("Игра (Steam Gift)"), "гифт")
        self.assertEqual(src.offer_kind("офлайн аккаунт"), "аккаунт")
        self.assertEqual(src.offer_kind("800 Robux пополнение"), "пополнение")

    def test_platform(self):
        self.assertEqual(src.offer_platform("key Xbox Series"), "Xbox")
        self.assertEqual(src.offer_platform("PS5 аккаунт"), "PlayStation")
        self.assertEqual(src.offer_platform("Steam Key"), "Steam")

    def test_dlc(self):
        self.assertTrue(src.is_dlc("Cyberpunk 2077 Phantom Liberty DLC"))
        self.assertFalse(src.is_dlc("Cyberpunk 2077 Ultimate + DLC"))

    def test_matches_dlc_and_bundles(self):
        ex = ["cyberpunk 2077 phantom liberty"]
        self.assertFalse(src.matches("Cyberpunk 2077", "CYBERPUNK 2077: PHANTOM LIBERTY XBOX КЛЮЧ", ex))
        self.assertTrue(src.matches("Cyberpunk 2077", "Cyberpunk 2077 + Phantom Liberty / Авто", ex))
        # «+» в «RU+МИР» не делает товар комплектом
        self.assertFalse(src.matches("ELDEN RING", "ELDEN RING NIGHTREIGN The Forsaken Hollows✅STEAM GIFT AUTO✅RU+МИР",
                                     ["elden ring nightreign the forsaken hollows", "elden ring nightreign"]))
        self.assertTrue(src.is_dlc("Baldur's Gate 3 - Digital Deluxe Edition DLC 🚀АВТО"))
        self.assertFalse(src.is_dlc("ELDEN RING Deluxe + NEW DLC (Steam)"))

    def test_parse_keeps_apostrophe(self):
        self.assertEqual(assistant.parse("baldur’s gate 3 ключ")["query"], "baldur's gate 3")

    def test_matches_excludes_series(self):
        self.assertTrue(src.matches("ELDEN RING", "ELDEN RING Steam Key", ["elden ring nightreign"]))
        self.assertFalse(src.matches("ELDEN RING", "ELDEN RING NIGHTREIGN key", ["elden ring nightreign"]))
        self.assertFalse(src.matches("Portal", "Portal 2 key", ["portal 2"]))

    def test_trust(self):
        self.assertEqual(src.trust(100, 1)[0], True)
        self.assertEqual(src.trust(4, 0)[0], False)
        self.assertEqual(src.trust(10, 2)[0], False)


class SearchTest(Base):
    async def test_search_filters_series_dlc(self):
        res = await self.svc.search("elden ring")
        titles = [o.title for o in res.offers]
        self.assertEqual(res.game.appid, 1245620)
        self.assertNotIn("ELDEN RING NIGHTREIGN ключ Steam", titles)
        self.assertNotIn("ELDEN RING - Tarnished Edition DLC Pack", titles)
        self.assertEqual(res.matched, 5)
        self.assertEqual(res.game.steam_review_pct, 93)

    async def test_sort_trusted_first(self):
        res = await self.svc.search("elden ring", kinds=["ключ"])
        self.assertTrue(res.offers[0].trusted)
        self.assertEqual(res.offers[0].price, 1700)  # Xbox ключ дешевле Steam, ненадёжный 1500 — в конце
        self.assertFalse(res.offers[-1].trusted)

    async def test_filters(self):
        res = await self.svc.search("elden ring", kinds=["ключ", "гифт"], platforms=["Steam"], trusted_only=True)
        self.assertEqual([o.price for o in res.offers], [1890, 2100])
        self.assertEqual(res.facets.kinds["аккаунт"], 1)

    async def test_non_steam_item(self):
        res = await self.svc.search("robux")
        self.assertIsNone(res.game)
        self.assertEqual(res.offers[0].kind, "пополнение")

    async def test_game_card_and_history(self):
        card = await self.svc.game_card(1245620)
        self.assertEqual(card.best["ключ"].price, 1700)
        self.assertEqual(card.best["гифт"].price, 2100)
        hist = self.svc.price_history("plati:1")
        self.assertEqual([p.price for p in hist.points], [1890])


class AssistantTest(Base):
    def test_parse(self):
        p = assistant.parse("где дешевле всего купить ключ cyberpunk 2077 в стим до 2000")
        self.assertEqual(p, {"query": "cyberpunk 2077", "kind": "ключ", "platform": "Steam", "max_price": 2000})
        p = assistant.parse("хочу робуксы до 1к")
        self.assertEqual((p["query"], p["kind"], p["max_price"]), ("robux", "пополнение", 1000))

    async def test_rules_answer(self):
        out = await assistant.answer(self.svc, AssistantIn(message="elden ring ключ стим до 2000"))
        self.assertEqual(out.engine, "rules")
        self.assertEqual(out.offers[0].price, 1890)
        self.assertIn("1 890 ₽", out.answer)

    async def test_rules_relaxes_kind(self):  # гифтов на Xbox нет — предлагаем ключ
        out = await assistant.answer(self.svc, AssistantIn(message="elden ring гифт xbox"))
        self.assertTrue(out.answer.startswith("Гифтов для Xbox сейчас нет"))
        self.assertEqual(out.offers[0].price, 1700)

    async def test_rules_relaxes_budget(self):
        out = await assistant.answer(self.svc, AssistantIn(message="elden ring ключ steam до 500"))
        self.assertIn("В 500 ₽ не уложиться", out.answer)
        self.assertEqual(out.offers[0].price, 1890)

    async def test_rules_empty(self):
        out = await assistant.answer(self.svc, AssistantIn(message="купить подешевле"))
        self.assertEqual(out.offers, [])


class OfficialStoresTest(Base):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        CHEAP_DEALS[:] = [
            {"title": "ELDEN RING", "dealID": "d1", "storeID": "1", "salePrice": "59.99", "normalPrice": "59.99", "thumb": "t"},
            {"title": "ELDEN RING", "dealID": "d2", "storeID": "7", "salePrice": "20.00", "normalPrice": "40.00", "thumb": "t"},
            {"title": "ELDEN RING", "dealID": "d3", "storeID": "7", "salePrice": "30.00", "normalPrice": "40.00", "thumb": "t"},
        ]

    async def asyncTearDown(self):
        CHEAP_DEALS.clear()
        await super().asyncTearDown()

    async def test_official_offers_in_rub(self):
        res = await self.svc.search("elden ring", kinds=["магазин"])
        self.assertEqual([(o.store, o.price) for o in res.offers], [("GOG", 1600), ("Steam", 4799)])
        gog = res.offers[0]
        self.assertEqual((gog.id, gog.platform, gog.old_price, gog.region), ("gog:1245620", "GOG", 3200, "GLOBAL"))
        self.assertEqual(res.matched, 7)
        self.assertEqual(res.facets.kinds["магазин"], 2)

    async def test_similar(self):
        await self.svc.search("elden ring")
        self.assertEqual(self.svc.db.similar(1245620), [])  # в каталоге одна игра — похожих нет

    async def test_catalog_and_deals(self):
        await self.svc.search("elden ring")
        cat = self.svc.catalog(10)
        self.assertEqual((cat[0].appid, cat[0].best_price, cat[0].official_price), (1245620, 1600, 1600))
        self.assertEqual({s["name"] for s in self.svc.db.stores()}, {"plati.market", "Steam", "GOG"})
        cur = self.svc.current(["plati:1", "gog:1245620"])
        self.assertEqual(sorted(o.price for o in cur), [1600, 1890])


class OfflineTest(Base):
    async def asyncTearDown(self):
        STATE["plati_down"] = False
        await super().asyncTearDown()

    async def test_falls_back_to_saved_prices(self):
        await self.svc.search("elden ring")       # цены попали в базу
        self.svc.cache.data.clear()
        STATE["plati_down"] = True
        src_sleep = src.asyncio.sleep
        src.asyncio.sleep = lambda *_: src_sleep(0)  # без пауз между повторами
        try:
            res = await self.svc.search("elden ring", kinds=["ключ"])
        finally:
            src.asyncio.sleep = src_sleep
        self.assertEqual(res.offers[0].price, 1700)
        self.assertIn("из базы", res.warnings[0])

    def test_region(self):
        self.assertEqual(src.offer_region("ELDEN RING Steam Key RU+CIS"), "RU")
        self.assertEqual(src.offer_region("Игра ключ (НЕ ДЛЯ РФ) Global"), "NO_RU")
        self.assertEqual(src.offer_region("Hades Steam Key GLOBAL"), "GLOBAL")
        self.assertIsNone(src.offer_region("Hades Steam Key"))


from app.nlu import model as nlu  # noqa: E402

try:
    import torch  # noqa: F401
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


@unittest.skipUnless(nlu.available(), "модель не обучена")
class NluTest(unittest.TestCase):
    def test_parse_buy(self):
        f = nlu.get().parse("ключ elden ring для стима до 2000")
        self.assertEqual((f.intent, f.kind, f.platform, f.max_price), ("buy", "ключ", "Steam", 2000))
        self.assertEqual(f.game.lower(), "elden ring")

    def test_parse_digits_in_name_vs_price(self):
        f = nlu.get().parse("cyberpunk 2077 гифтом до 1.5к")
        self.assertEqual((f.game.lower(), f.kind, f.max_price), ("cyberpunk 2077", "гифт", 1500))

    def test_parse_other_intents(self):
        m = nlu.get()
        self.assertEqual(m.parse("что такое гифт").intent, "faq")
        self.assertEqual(m.parse("привет").intent, "greet")
        self.assertEqual(m.parse("как приготовить борщ").intent, "other")
        f = m.parse("посоветуй рпг до 1000")
        self.assertEqual((f.intent, f.genre, f.max_price), ("recommend", "ролев", 1000))

    def test_resolve(self):
        self.assertEqual(nlu.resolve("гта 5"), "Grand Theft Auto V")
        self.assertEqual(nlu.resolve("elden rign", ["ELDEN RING", "Hades"]), "ELDEN RING")
        self.assertEqual(nlu.resolve("hades 2", ["Hades"]), "hades 2")  # другая цифра — другая игра

    @unittest.skipUnless(HAS_TORCH, "нет PyTorch")
    def test_numpy_matches_torch(self):
        """Инференс на numpy считает то же, что обученная сеть в PyTorch."""
        import torch
        from app.nlu import train
        from app.nlu.features import sentence_feats
        torch.manual_seed(0)
        net = train.Net().eval()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "w.npz"
            train.export(net, path)
            words = ["ключ", "elden", "ring", "до", "2000"]
            m = nlu.ShopNLU(path, Path(d) / "нет.json")
            np_out = m.forward(words)
            with torch.no_grad():
                X = torch.tensor([sentence_feats(words)])
                net.emb.weight.data = net.emb.weight.data.half().float()  # в файле эмбеддинги в float16
                t_out = net(X, torch.tensor([len(words)]))
        for a, b in zip(np_out, t_out):
            self.assertLess(float(abs(torch.tensor(a) - b.squeeze(0)).max()), 1e-4)


@unittest.skipUnless(nlu.available(), "модель не обучена")
class SmartAssistantTest(Base):
    async def ask(self, text, **kw):
        return await assistant.answer(self.svc, AssistantIn(message=text, **kw), engine="model")

    async def test_buy(self):
        out = await self.ask("elden ring ключ стим до 2000")
        self.assertEqual((out.engine, out.nlu.intent), ("model", "buy"))
        self.assertEqual(out.offers[0].price, 1890)

    async def test_profile_and_history(self):
        from app.schemas import ChatTurn, Profile
        out = await self.ask("а гифтом?", history=[ChatTurn(role="user", text="elden ring ключ")],
                             profile=Profile(platform="Steam"))
        self.assertEqual(out.offers[0].price, 2100)  # игра из прошлой реплики, платформа из профиля
        self.assertIn("ELDEN RING", out.answer)

    async def test_review(self):
        out = await self.ask("стоит ли брать elden ring")
        self.assertEqual(out.nlu.intent, "review")
        self.assertIn("93%", out.answer)
        self.assertIn("Metacritic — 94", out.answer)

    async def test_compare(self):
        CHEAP_DEALS[:] = [{"title": "ELDEN RING", "dealID": "d1", "storeID": "1", "salePrice": "59.99", "normalPrice": "59.99"}]
        try:
            out = await self.ask("сравни цены на elden ring")
        finally:
            CHEAP_DEALS.clear()
        self.assertEqual(out.nlu.intent, "compare")
        self.assertIn("официальных магазинах — от 4 799 ₽", out.answer)
        self.assertIn("У продавцов дешевле на 3 099 ₽ (65%)", out.answer)  # ключ Xbox 1700 против 4799

    async def test_recommend_from_catalog(self):
        await self.svc.search("elden ring")  # игра попадает в каталог
        out = await self.ask("посоветуй рпг до 2000")
        self.assertEqual(out.nlu.intent, "recommend")
        self.assertIn("ELDEN RING", out.answer)
        self.assertEqual(out.offers[0].price, 1700)  # лучшее надёжное предложение игры

    async def test_faq_greet_other(self):
        self.assertIn("подарок через Steam", (await self.ask("что такое гифт")).answer)
        self.assertIn("Умею", (await self.ask("привет")).answer)
        self.assertIn("только с играми", (await self.ask("как приготовить борщ")).answer)


class ApiTest(unittest.TestCase):
    """HTTP-уровень: регистрация, вход, профиль, избранное, блокировка."""

    def setUp(self):
        from fastapi.testclient import TestClient
        from app import main
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self.tmp.name
        self.client = TestClient(main.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.tmp.cleanup()
        os.environ.pop("DATA_DIR", None)

    def test_auth_flow(self):
        c = self.client
        r = c.post("/api/auth/register", json={"email": "a@b.ru", "password": "secret123", "name": "Аня"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIn("us_session", r.cookies)
        self.assertEqual(c.post("/api/auth/register", json={"email": "A@b.ru", "password": "secret123"}).status_code, 409)
        r = c.put("/api/me/profile", json={"budget": 2000, "platform": "Steam", "kinds": ["ключ", "магазин"]})
        self.assertEqual(r.json()["profile"]["budget"], 2000)
        r = c.put("/api/me/favorites", json=[{"offer_id": "plati:1", "title": "ELDEN RING", "price": 1890}])
        self.assertEqual(r.json()["favorites"][0]["offer_id"], "plati:1")
        c.post("/api/auth/logout")
        self.assertEqual(c.get("/api/me").status_code, 401)
        r = c.post("/api/auth/login", json={"email": "a@b.ru", "password": "secret123"})
        self.assertEqual(r.json()["profile"]["platform"], "Steam")
        token = r.json()["token"]
        c.cookies.clear()
        self.assertEqual(c.get("/api/me", headers={"Authorization": f"Bearer {token}"}).status_code, 200)

    def test_lockout_and_validation(self):
        c = self.client
        self.assertEqual(c.post("/api/auth/register", json={"email": "bad", "password": "secret123"}).status_code, 422)
        self.assertEqual(c.post("/api/auth/register", json={"email": "x@y.ru", "password": "short"}).status_code, 422)
        c.post("/api/auth/register", json={"email": "x@y.ru", "password": "secret123"})
        codes = [c.post("/api/auth/login", json={"email": "x@y.ru", "password": "wrongpass"}).status_code for _ in range(5)]
        self.assertEqual(codes, [401] * 5)
        self.assertEqual(c.post("/api/auth/login", json={"email": "x@y.ru", "password": "secret123"}).status_code, 429)

    def test_feedback_stats(self):
        c = self.client
        for h in (True, True, False):
            self.assertEqual(c.post("/api/feedback", json={"helpful": h, "where": "assistant"}).status_code, 200)
        st = c.get("/api/feedback/stats").json()
        self.assertEqual((st["total"], st["helpful"], st["helpful_pct"]), (3, 2, 67))
        self.assertEqual(c.post("/api/feedback", json={"helpful": True, "where": "чужое"}).status_code, 422)

    def test_favorite_target_price(self):
        c = self.client
        c.post("/api/auth/register", json={"email": "t@t.ru", "password": "secret123"})
        r = c.put("/api/me/favorites", json=[{"offer_id": "plati:1", "price": 1890, "target_price": 1500, "kind": "ключ"}])
        self.assertEqual(r.json()["favorites"][0]["target_price"], 1500)

    def test_catalog_endpoints_empty(self):
        self.assertEqual(self.client.get("/api/catalog").json(), [])
        self.assertEqual(self.client.get("/api/deals").json(), [])
        self.assertEqual(self.client.get("/api/nope").status_code, 404)


if __name__ == "__main__":
    unittest.main()
