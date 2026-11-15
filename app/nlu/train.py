"""Обучение ShopNLU (нужен PyTorch: pip install -r requirements-train.txt).

    python -m app.nlu.train                  # ~2 мин на CPU: датасет → обучение → метрики → app/nlu/shopnlu.npz
    python -m app.nlu.train --epochs 20 --n 40000

Пишет веса (npz), описание и метрики (shopnlu.json) и отчёт docs/МОДЕЛЬ_метрики.md.
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence

from . import dataset
from .features import BUCKETS, INTENTS, KINDS, PLATFORMS, TAGS, sentence_feats
from .model import META, WEIGHTS, ShopNLU, _n

ROOT = Path(__file__).resolve().parents[2]


class Net(nn.Module):
    def __init__(self, dim: int = 48, hidden: int = 64, dropout: float = 0.25):
        super().__init__()
        self.emb = nn.Embedding(BUCKETS, dim, padding_idx=0)
        self.gru = nn.GRU(dim, hidden, batch_first=True, bidirectional=True)
        self.drop = nn.Dropout(dropout)
        self.tag = nn.Linear(2 * hidden, len(TAGS))
        self.intent = nn.Linear(4 * hidden, len(INTENTS))
        self.kind = nn.Linear(4 * hidden, len(KINDS))
        self.platform = nn.Linear(4 * hidden, len(PLATFORMS))

    def forward(self, X, lengths):
        e = self.emb(X)                                            # B×T×K×D
        cnt = (X > 0).sum(-1, keepdim=True).clamp(min=1)
        x = self.drop(e.sum(2) / cnt)                              # B×T×D
        T = X.shape[1]
        packed = pack_padded_sequence(x, lengths.cpu(), batch_first=True, enforce_sorted=False)
        h, _ = self.gru(packed)
        h, _ = pad_packed_sequence(h, batch_first=True, total_length=T)
        mask = (torch.arange(T)[None, :] < lengths[:, None]).unsqueeze(-1)
        mx = h.masked_fill(~mask, -1e4).max(1).values
        mean = (h * mask).sum(1) / lengths[:, None]
        pooled = self.drop(torch.cat([mx, mean], -1))
        return self.tag(self.drop(h)), self.intent(pooled), self.kind(pooled), self.platform(pooled)


def tensorize(batch: list[dict]):
    T = max(len(ex["tokens"]) for ex in batch)
    K = len(sentence_feats(["x"])[0])
    X = torch.zeros(len(batch), T, K, dtype=torch.long)
    Y = torch.full((len(batch), T), -100, dtype=torch.long)
    for i, ex in enumerate(batch):
        X[i, :len(ex["tokens"])] = torch.tensor(ex["feats"])
        Y[i, :len(ex["tags"])] = torch.tensor([TAGS.index(t) for t in ex["tags"]])
    L = torch.tensor([len(ex["tokens"]) for ex in batch])
    yi = torch.tensor([INTENTS.index(ex["intent"]) for ex in batch])
    yk = torch.tensor([KINDS.index(ex["kind"]) for ex in batch])
    yp = torch.tensor([PLATFORMS.index(ex["platform"]) for ex in batch])
    return X, L, Y, yi, yk, yp


def export(net: Net, path: Path) -> None:
    sd = {k: v.detach().cpu().numpy() for k, v in net.state_dict().items()}
    w = {"emb": sd["emb.weight"].astype(np.float16),  # таблица эмбеддингов — в половинной точности, файл вдвое меньше
         "tag_w": sd["tag.weight"], "tag_b": sd["tag.bias"]}
    for d, suf in (("f", ""), ("b", "_reverse")):
        for a, b in (("wih", "weight_ih_l0"), ("whh", "weight_hh_l0"), ("bih", "bias_ih_l0"), ("bhh", "bias_hh_l0")):
            w[f"gru_{d}_{a}"] = sd[f"gru.{b}{suf}"]
    for k in ("intent", "kind", "platform"):
        w[f"{k}_w"], w[f"{k}_b"] = sd[f"{k}.weight"], sd[f"{k}.bias"]
    np.savez_compressed(path, **w)


# ── оценка (той же numpy-моделью, что работает на сайте) ─────────

def evaluate_frames(model: ShopNLU, rows: list[dict]) -> dict:
    """rows: {text, intent, kind, platform, game, price, genre} — метрики по полям и доля полностью верных разборов."""
    ok = Counter()
    errors = []
    for r in rows:
        f = model.parse(r["text"])
        got = {"intent": f.intent, "kind": f.kind or "any", "platform": f.platform or "any",
               "game": _n(f.game) if f.game else None, "price": f.max_price, "genre": f.genre}
        exp = {k: (_n(r[k]) if k == "game" and r[k] else r[k]) for k in got}
        good = {k: got[k] == exp[k] for k in got}
        ok.update(k for k, v in good.items() if v)
        if all(good.values()):
            ok["frame"] += 1
        else:
            errors.append({"text": r["text"], **{k: f"{got[k]} (надо {exp[k]})" for k in got if not good[k]}})
    n = len(rows)
    return {"n": n, **{k: round(ok[k] / n, 3) for k in ("intent", "kind", "platform", "game", "price", "genre", "frame")},
            "errors": errors}


def tagging_f1(model: ShopNLU, examples: list[dict]) -> dict:
    """Точность классификаторов и F1 по выделенным кускам (игра/цена/жанр) на сгенерированных примерах."""
    tp = fp = fn = 0
    acc = Counter()
    for ex in examples:
        tag_logits, il, kl, pl = model.forward(ex["tokens"])
        from .model import _softmax, _spans, viterbi
        pred = [TAGS[i] for i in viterbi(np.log(_softmax(tag_logits) + 1e-9))]
        ps = {(k, s) for k, v in _spans(pred).items() for s in v}
        gs = {(k, s) for k, v in _spans(ex["tags"]).items() for s in v}
        tp, fp, fn = tp + len(ps & gs), fp + len(ps - gs), fn + len(gs - ps)
        acc["intent"] += INTENTS[int(il.argmax())] == ex["intent"]
        acc["kind"] += KINDS[int(kl.argmax())] == ex["kind"]
        acc["platform"] += PLATFORMS[int(pl.argmax())] == ex["platform"]
    n = len(examples)
    p, r = tp / max(tp + fp, 1), tp / max(tp + fn, 1)
    return {"n": n, "slot_f1": round(2 * p * r / max(p + r, 1e-9), 3),
            **{k: round(v / n, 3) for k, v in acc.items()}}


def load_jsonl(name: str) -> list[dict]:
    text = (Path(__file__).parent / "data" / name).read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def catalog_titles() -> list[str]:
    db = ROOT / "data" / "shop.db"
    if not db.exists():
        return []
    con = sqlite3.connect(str(db))
    try:
        return [r[0] for r in con.execute("SELECT title FROM product")]
    finally:
        con.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30000, help="сколько примеров сгенерировать для обучения")
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--seed", type=int, default=13)
    a = ap.parse_args()
    random.seed(a.seed)
    torch.manual_seed(a.seed)
    torch.set_num_threads(max(1, torch.get_num_threads()))

    t0 = time.time()
    train_games, held_games = dataset.split_games(catalog_titles())
    train = dataset.generate(a.n, train_games, seed=a.seed)
    dev = dataset.generate(2000, held_games, seed=a.seed + 100)        # игры, которых не было в обучении
    for ex in train + dev:
        ex["feats"] = sentence_feats(ex["tokens"])
    print(f"датасет: {len(train)} обучение, {len(dev)} проверка; игр {len(train_games)} + {len(held_games)} отложено "
          f"({time.time() - t0:.1f} с)")
    print("намерения:", dict(Counter(ex["intent"] for ex in train)))

    net = Net()
    opt = torch.optim.AdamW(net.parameters(), lr=3e-3, weight_decay=1e-5)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=4e-3, total_steps=a.epochs * (len(train) // 64 + 1))
    ce = nn.CrossEntropyLoss()
    ce_tag = nn.CrossEntropyLoss(ignore_index=-100)
    best, best_state = -1.0, None
    manual = load_jsonl("test_manual.jsonl")
    blind = load_jsonl("test_blind.jsonl")
    for epoch in range(1, a.epochs + 1):
        net.train()
        random.shuffle(train)
        total = 0.0
        for i in range(0, len(train), 64):
            X, L, Y, yi, yk, yp = tensorize(train[i:i + 64])
            tag, il, kl, pl = net(X, L)
            loss = ce_tag(tag.reshape(-1, len(TAGS)), Y.reshape(-1)) + ce(il, yi) + 0.7 * ce(kl, yk) + 0.7 * ce(pl, yp)
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(net.parameters(), 5.0)
            opt.step()
            sched.step()
            total += loss.item() * len(X)
        net.eval()
        with torch.no_grad():
            export(net, WEIGHTS)
        m = ShopNLU(WEIGHTS)
        d = tagging_f1(m, dev[:800])
        score = d["slot_f1"] + d["intent"] + 0.5 * (d["kind"] + d["platform"])
        print(f"эпоха {epoch:2d}: loss {total / len(train):.3f} · новые игры: намерение {d['intent']:.3f}, "
              f"тип {d['kind']:.3f}, платформа {d['platform']:.3f}, F1 слотов {d['slot_f1']:.3f}")
        if score > best:
            best, best_state = score, {k: v.clone() for k, v in net.state_dict().items()}

    net.load_state_dict(best_state)
    export(net, WEIGHTS)
    model = ShopNLU(WEIGHTS)
    dev_m = tagging_f1(model, dev)
    man = evaluate_frames(model, manual)
    bl = evaluate_frames(model, blind)
    params = sum(p.numel() for p in net.parameters())
    meta = {
        "name": "ShopNLU", "version": time.strftime("%Y-%m-%d"), "params": params,
        "architecture": "hash-эмбеддинги слов и n-грамм (48) → BiGRU 2×64 → метки слов (Витерби) + намерение/тип/платформа",
        "labels": {"tags": TAGS, "intents": INTENTS, "kinds": KINDS, "platforms": PLATFORMS},
        "data": {"train": len(train), "dev_unseen_games": len(dev), "train_games": len(train_games),
                 "held_out_games": len(held_games), "manual_test": len(manual), "blind_test": len(blind)},
        "metrics": {"dev_unseen_games": dev_m, "manual_test": {k: v for k, v in man.items() if k != "errors"},
                    "blind_test": {k: v for k, v in bl.items() if k != "errors"}},
        "train_seconds": round(time.time() - t0),
    }
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    report = ROOT / "docs" / "МОДЕЛЬ_метрики.md"
    lines = [f"# ShopNLU — метрики ({meta['version']})", "",
             f"Параметров: {params:,}".replace(",", " ") + f" · файл весов {WEIGHTS.stat().st_size // 1024} КБ · обучение {meta['train_seconds']} с", "",
             "| Набор | Намерение | Тип товара | Платформа | Игра | Цена | Жанр | Разбор целиком |", "|---|---|---|---|---|---|---|---|",
             f"| Ручной тест ({man['n']}; по его ошибкам дополняли генератор) | {man['intent']:.0%} | {man['kind']:.0%} | {man['platform']:.0%} | {man['game']:.0%} | "
             f"{man['price']:.0%} | {man['genre']:.0%} | {man['frame']:.0%} |",
             f"| Слепой тест ({bl['n']}, написан после первой версии, в подборе не участвовал) | {bl['intent']:.0%} | {bl['kind']:.0%} | "
             f"{bl['platform']:.0%} | {bl['game']:.0%} | {bl['price']:.0%} | {bl['genre']:.0%} | {bl['frame']:.0%} |",
             f"| Сгенерированные, незнакомые игры ({dev_m['n']}) | {dev_m['intent']:.0%} | {dev_m['kind']:.0%} | {dev_m['platform']:.0%} | "
             f"F1 слотов {dev_m['slot_f1']:.0%} | | | |", "", "## Ошибки на ручном тесте", ""]
    fmt = lambda errs: [f"- «{e['text']}»: " + "; ".join(f"{k} = {v}" for k, v in e.items() if k != "text") for e in errs] or ["нет"]
    lines += fmt(man["errors"]) + ["", "## Ошибки на слепом тесте", ""] + fmt(bl["errors"])
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(meta["metrics"], ensure_ascii=False, indent=1))
    print(f"ошибок: ручной тест {len(man['errors'])}, слепой {len(bl['errors'])} — см. {report}")


if __name__ == "__main__":
    main()
