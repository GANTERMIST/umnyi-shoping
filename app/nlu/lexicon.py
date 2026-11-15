"""Словари проекта: названия игр и их народные варианты, жанры, числа прописью.

Используются и генератором обучающих данных, и нормализацией того, что выделила модель
(«гта 5» → «Grand Theft Auto V», «рпг» → жанр «Ролевые игры», «полторы тысячи» → 1500).
"""
from __future__ import annotations

import re

# Популярные игры (англ. названия как в Steam). Часть уйдёт в обучение, часть — в проверку на незнакомых.
GAMES = """Elden Ring|Cyberpunk 2077|Baldur's Gate 3|Red Dead Redemption 2|Grand Theft Auto V|The Witcher 3: Wild Hunt|
Hogwarts Legacy|Stardew Valley|Terraria|Hades|Hades II|Sekiro: Shadows Die Twice|Dark Souls III|Rust|Valheim|Palworld|
Helldivers 2|God of War|Forza Horizon 5|Resident Evil 4|Hollow Knight|Monster Hunter Wilds|Black Myth: Wukong|
Sid Meier's Civilization VI|Euro Truck Simulator 2|DayZ|Dead by Daylight|Satisfactory|Factorio|RimWorld|Project Zomboid|
Lethal Company|It Takes Two|Detroit: Become Human|Kingdom Come: Deliverance II|The Elder Scrolls V: Skyrim|Fallout 4|
DOOM Eternal|Subnautica|The Forest|Sons of the Forest|Phasmophobia|Ready or Not|Hearts of Iron IV|Cities: Skylines|
Mount & Blade II: Bannerlord|No Man's Sky|Counter-Strike 2|Dota 2|PUBG: Battlegrounds|Apex Legends|Call of Duty|
Rainbow Six Siege|Warframe|War Thunder|Overwatch 2|Deadlock|Slay the Spire|Slay the Spire 2|Geometry Dash|R.E.P.O.|
The Binding of Isaac: Rebirth|Wallpaper Engine|Battlefield 6|Battlefield 2042|Starfield|Diablo IV|Path of Exile 2|
Lies of P|Sea of Thieves|Deep Rock Galactic|Risk of Rain 2|Celeste|Cuphead|Dead Cells|Hotline Miami|Portal 2|
Half-Life: Alyx|Left 4 Dead 2|Team Fortress 2|Garry's Mod|Among Us|Fall Guys|Rocket League|Minecraft|Roblox|Fortnite|
Genshin Impact|Honkai: Star Rail|Zenless Zone Zero|Brawl Stars|Standoff 2|PUBG Mobile|Valorant|League of Legends|
Assassin's Creed Shadows|Assassin's Creed Valhalla|Far Cry 6|Watch Dogs 2|The Last of Us Part I|Ghost of Tsushima|
Horizon Zero Dawn|Spider-Man Remastered|Death Stranding|Metro Exodus|S.T.A.L.K.E.R. 2|Atomic Heart|Mortal Kombat 1|
Tekken 8|Street Fighter 6|EA Sports FC 25|NBA 2K25|F1 24|Need for Speed Unbound|Dying Light 2|Days Gone|
Frostpunk 2|Manor Lords|Anno 1800|Total War: Warhammer III|Crusader Kings III|Stellaris|XCOM 2|Disco Elysium|
Divinity: Original Sin 2|Pathfinder: Wrath of the Righteous|Mass Effect Legendary Edition|Dragon Age: The Veilguard|
Persona 5 Royal|Final Fantasy VII Remake|Nier: Automata|Dark Souls Remastered|Armored Core VI|Balatro|Vampire Survivors|
Brotato|Content Warning|Schedule I|Peak|Raft|Green Hell|Grounded|Outlast|Amnesia: The Bunker|Alan Wake 2|
Silent Hill 2|Resident Evil Village|Dead Space|Control|Hitman 3|Prey|Dishonored 2|BioShock Infinite|Borderlands 3|
Titanfall 2|Payday 3|Payday 2|Arma 3|Squad|Escape from Tarkov|Hunt: Showdown|The Finals|Marvel Rivals|
Euro Truck Simulator|American Truck Simulator|Microsoft Flight Simulator|Farming Simulator 25|Planet Zoo|
Two Point Hospital|The Sims 4|Spore|Portal|Undertale|Deltarune|Oxygen Not Included|Don't Starve Together|Terraria Calamity""".replace("\n", "").split("|")

# Народные и русские названия → как искать в магазинах
ALIASES = {
    "элден ринг": "Elden Ring", "элден": "Elden Ring", "елден ринг": "Elden Ring", "кольцо элдена": "Elden Ring",
    "киберпанк": "Cyberpunk 2077", "киберпанк 2077": "Cyberpunk 2077", "сайберпанк": "Cyberpunk 2077",
    "бг3": "Baldur's Gate 3", "бг 3": "Baldur's Gate 3", "балдурс гейт 3": "Baldur's Gate 3", "балдур": "Baldur's Gate 3",
    "балдурс гейт": "Baldur's Gate 3", "baldurs gate 3": "Baldur's Gate 3", "bg3": "Baldur's Gate 3",
    "рдр 2": "Red Dead Redemption 2", "рдр2": "Red Dead Redemption 2", "рдр": "Red Dead Redemption 2", "rdr 2": "Red Dead Redemption 2",
    "rdr2": "Red Dead Redemption 2", "ред дед": "Red Dead Redemption 2", "ред дед редемпшн 2": "Red Dead Redemption 2",
    "гта 5": "Grand Theft Auto V", "гта": "Grand Theft Auto V", "гта v": "Grand Theft Auto V", "gta 5": "Grand Theft Auto V",
    "gta v": "Grand Theft Auto V", "gta": "Grand Theft Auto V", "гташка": "Grand Theft Auto V",
    "ведьмак": "The Witcher 3", "ведьмак 3": "The Witcher 3", "ведьмака 3": "The Witcher 3", "ведьмака": "The Witcher 3",
    "witcher 3": "The Witcher 3", "хогвартс": "Hogwarts Legacy", "хогвартс легаси": "Hogwarts Legacy",
    "хогвартс наследие": "Hogwarts Legacy", "стардью": "Stardew Valley", "стардью валли": "Stardew Valley",
    "террария": "Terraria", "террарию": "Terraria", "хадес": "Hades", "аид": "Hades", "секиро": "Sekiro",
    "дарк соулс 3": "Dark Souls III", "дарк соулс": "Dark Souls III", "ds3": "Dark Souls III", "раст": "Rust",
    "вальхейм": "Valheim", "палворлд": "Palworld", "хеллдайверс 2": "Helldivers 2", "хеллдайверс": "Helldivers 2",
    "хелдайверс": "Helldivers 2", "год оф вар": "God of War", "форза 5": "Forza Horizon 5", "форза": "Forza Horizon 5",
    "резидент 4": "Resident Evil 4", "ре4": "Resident Evil 4", "холлоу найт": "Hollow Knight", "вуконг": "Black Myth Wukong",
    "цивилизация 6": "Civilization VI", "цива 6": "Civilization VI", "цива": "Civilization VI", "етс 2": "Euro Truck Simulator 2",
    "етс2": "Euro Truck Simulator 2", "дальнобойщики": "Euro Truck Simulator 2", "дейз": "DayZ", "дбд": "Dead by Daylight",
    "дед бай дейлайт": "Dead by Daylight", "сатисфактори": "Satisfactory", "факторио": "Factorio", "римворлд": "RimWorld",
    "зомбоид": "Project Zomboid", "проджект зомбоид": "Project Zomboid", "летал компани": "Lethal Company",
    "ит тейкс ту": "It Takes Two", "детройт": "Detroit Become Human", "kcd2": "Kingdom Come Deliverance II",
    "кингдом кам 2": "Kingdom Come Deliverance II", "кингдом кам": "Kingdom Come Deliverance II", "скайрим": "Skyrim",
    "фоллаут 4": "Fallout 4", "фолыч 4": "Fallout 4", "фолыч": "Fallout 4", "дум": "DOOM Eternal", "сабнатика": "Subnautica",
    "фазмофобия": "Phasmophobia", "фазма": "Phasmophobia", "хойка": "Hearts of Iron IV", "хои 4": "Hearts of Iron IV",
    "hoi4": "Hearts of Iron IV", "ситис скайлайнс": "Cities Skylines", "баннерлорд": "Bannerlord", "но мэнс скай": "No Man's Sky",
    "кс": "Counter-Strike 2", "кс 2": "Counter-Strike 2", "кс2": "Counter-Strike 2", "ксго": "Counter-Strike 2", "cs2": "Counter-Strike 2",
    "cs 2": "Counter-Strike 2", "контра": "Counter-Strike 2", "дота": "Dota 2", "дота 2": "Dota 2", "пабг": "PUBG", "пубг": "PUBG",
    "апекс": "Apex Legends", "колда": "Call of Duty", "кол оф дьюти": "Call of Duty", "радуга": "Rainbow Six Siege",
    "р6": "Rainbow Six Siege", "варфрейм": "Warframe", "вар тандер": "War Thunder", "тундра": "War Thunder",
    "овервотч": "Overwatch", "дедлок": "Deadlock", "слей зе спаер": "Slay the Spire", "репо": "R.E.P.O.",
    "айзек": "The Binding of Isaac", "обои": "Wallpaper Engine", "валпейпер": "Wallpaper Engine", "батла 6": "Battlefield 6",
    "батла": "Battlefield 6", "батлфилд 6": "Battlefield 6", "старфилд": "Starfield", "диабло 4": "Diablo IV", "диабло": "Diablo IV",
    "пое 2": "Path of Exile 2", "майнкрафт": "Minecraft", "майн": "Minecraft", "роблокс": "Roblox", "фортнайт": "Fortnite",
    "геншин": "Genshin Impact", "хонкай": "Honkai Star Rail", "бравл старс": "Brawl Stars", "бравл": "Brawl Stars",
    "стандофф 2": "Standoff 2", "стендофф": "Standoff 2", "валорант": "Valorant", "лол": "League of Legends",
    "сталкер 2": "S.T.A.L.K.E.R. 2", "сталкер": "S.T.A.L.K.E.R. 2", "атомик харт": "Atomic Heart", "атомное сердце": "Atomic Heart",
    "мортал комбат": "Mortal Kombat 1", "мк1": "Mortal Kombat 1", "фифа": "EA Sports FC 25", "фкашка": "EA Sports FC 25",
    "дайн лайт 2": "Dying Light 2", "даинг лайт 2": "Dying Light 2", "метро": "Metro Exodus", "метро исход": "Metro Exodus",
    "диско элизиум": "Disco Elysium", "балатро": "Balatro", "вампир сурвайворс": "Vampire Survivors", "тарков": "Escape from Tarkov",
    "симс 4": "The Sims 4", "симс": "The Sims 4", "андертейл": "Undertale", "донт старв": "Don't Starve Together",
    "пейдей 2": "Payday 2", "пейдей": "Payday 3", "лиес оф пи": "Lies of P", "си оф тивс": "Sea of Thieves",
    "дип рок": "Deep Rock Galactic", "ризк оф рейн 2": "Risk of Rain 2", "портал 2": "Portal 2", "халф лайф": "Half-Life Alyx",
    # пополнения и валюта
    "робуксы": "robux", "робуксов": "robux", "робукс": "robux", "робаксы": "robux", "robux": "robux",
    "вбаксы": "v-bucks", "в-баксы": "v-bucks", "в баксы": "v-bucks", "вибаксы": "v-bucks", "v-bucks": "v-bucks", "vbucks": "v-bucks",
    "примогемы": "genshin impact кристаллы", "кристаллы геншин": "genshin impact кристаллы", "кристаллы genshin": "genshin impact кристаллы",
    "гемы бравл старс": "brawl stars гемы", "гемы": "brawl stars гемы", "голда стандофф": "standoff 2 голда",
    "голду стандофф 2": "standoff 2 голда", "голду": "standoff 2 голда", "юси": "pubg mobile uc", "uc пубг": "pubg mobile uc",
    "стим кошелек": "steam пополнение", "кошелек стим": "steam пополнение", "баланс стим": "steam пополнение",
    "стим баланс": "steam пополнение", "steam wallet": "steam пополнение", "пс плюс": "playstation plus",
    "гейм пасс": "xbox game pass", "game pass": "xbox game pass", "геймпасс": "xbox game pass",
}

# Предметы пополнения (для генератора; модель размечает их как «товар» — тот же слот, что и игра)
TOPUP_ITEMS = ["робуксы", "robux", "в-баксы", "v-bucks", "примогемы", "кристаллы genshin", "гемы бравл старс",
               "голду стандофф 2", "uc пубг", "стим кошелек", "баланс стим", "steam wallet", "пс плюс", "game pass",
               "робуксов", "робаксы", "вбаксы", "гемы", "голду", "юси"]

# Жанры: что говорят люди → корень, по которому ищем в жанрах Steam
GENRE_WORDS = {
    "рпг": "ролев", "rpg": "ролев", "ролевую": "ролев", "ролевую игру": "ролев", "ролевуху": "ролев", "ролевые": "ролев",
    "шутер": "экшен", "шутеры": "экшен", "стрелялку": "экшен", "экшен": "экшен", "экшн": "экшен", "боевик": "экшен",
    "стратегию": "стратег", "стратегии": "стратег", "стратегия": "стратег", "симулятор": "симулятор", "симуляторы": "симулятор",
    "инди": "инди", "индюшку": "инди", "гонки": "гонк", "гоночную": "гонк", "гонку": "гонк", "приключение": "приключ",
    "приключения": "приключ", "адвенчуру": "приключ", "казуалку": "казуал", "казуальную": "казуал", "спортивную": "спорт",
    "спорт": "спорт", "кооп": "многопольз", "кооператив": "многопольз", "кооперативную": "многопольз", "мультиплеер": "многопольз",
    "онлайн игру": "многопольз", "мморпг": "многопольз", "mmo": "многопольз", "ммо": "многопольз", "рпгшек": "ролев", "гонок": "гонк", "хоррор": "экшен", "ужастик": "экшен", "выживание": "приключ",
    "выживалку": "приключ", "рогалик": "инди", "рогалик ": "инди", "головоломку": "казуал", "песочницу": "симулятор",
}

NUM_WORDS = {
    "один": 1, "одна": 1, "одну": 1, "два": 2, "две": 2, "двух": 2, "три": 3, "трех": 3, "четыре": 4, "четырех": 4,
    "пять": 5, "пяти": 5, "шесть": 6, "семь": 7, "восемь": 8, "десять": 10, "полторы": 1.5, "полтора": 1.5,
    "полутора": 1.5, "сто": 100, "сотку": 100, "сотни": 100, "двести": 200, "двухсот": 200, "триста": 300, "трехсот": 300,
    "четыреста": 400, "пятьсот": 500, "пятисот": 500, "шестьсот": 600, "семьсот": 700, "восемьсот": 800, "девятьсот": 900,
    "тысяча": 1000, "тысячу": 1000, "тысячи": 1000, "тыщу": 1000, "тыщи": 1000, "косарь": 1000, "косаря": 1000,
    "косарей": 1000, "тысяч": 1000,
}
THOUSAND = {"к", "k", "тыс", "тысяч", "тысячи", "тысяча", "тысячу", "тыщ", "тыщи", "тыщу", "косарей", "косаря", "косарь", "кусков"}


def parse_price(words: list[str]) -> float | None:
    """Слова, которые модель отметила как цену → число рублей: «1.5к», «2 тысячи», «полторы тыщи», «1 500»."""
    cur: float | None = None
    for w in words:
        m = re.fullmatch(r"(\d+(?:[.,]\d+)?)([кk]|тыс)?(?:р|руб|rub|r)?", w)
        if m:
            n = float(m.group(1).replace(",", "."))
            if m.group(2):
                cur = n * 1000
            elif cur is not None and cur < 1000 and len(m.group(1)) == 3 and cur == int(cur):
                cur = cur * 1000 + n  # «1 500»
            else:
                cur = n
        elif w in THOUSAND:
            cur = (cur if cur and cur < 1000 else 1) * 1000 if not (cur and cur >= 1000) else cur
        elif w in NUM_WORDS:
            n = NUM_WORDS[w]
            if n == 1000:
                cur = (cur if cur and cur < 1000 else 1) * 1000
            elif cur and cur >= 1000:
                cur += n
            else:
                cur = n if cur is None else cur * n if n < 10 else cur + n
    return cur if cur and cur >= 10 else None


def genre_stem(words: list[str]) -> str | None:
    text = " ".join(words)
    if text in GENRE_WORDS:
        return GENRE_WORDS[text]
    for w in words:
        for k, v in GENRE_WORDS.items():
            if w == k or (len(w) > 4 and w[:5] == k[:5]):
                return v
    return None
