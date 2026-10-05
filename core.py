"""KiranaVoice core: database, intent parser, demand forecasting (no Streamlit here)."""
import json
import math
import random
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from difflib import get_close_matches
from functools import lru_cache

import pandas as pd
import requests

from i18n import ITEM_TRANSLATIONS

DB_FILE = "kirana_inventory.db"
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "gemma2:2b"
IST = timezone(timedelta(hours=5, minutes=30))

# Edit this list every year (shop-level festival calendar used as a forecast feature)
FESTIVALS = {date(2026, 10, 20), date(2026, 11, 8)}


def now_ist() -> datetime:
    return datetime.now(IST)


# ---------------------------------------------------------------- DATABASE
def get_conn():
    conn = sqlite3.connect(DB_FILE, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


@contextmanager
def db():
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    conn = get_conn()
    conn.execute("PRAGMA journal_mode=WAL")  # persistent; set once
    conn.close()
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS inventory (
            item TEXT PRIMARY KEY, category TEXT DEFAULT 'General',
            current_stock REAL NOT NULL, unit TEXT NOT NULL,
            reorder_level REAL DEFAULT 10, updated_at TEXT);
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT UNIQUE,
            raw_text TEXT, item TEXT, action TEXT, qty REAL, applied_qty REAL,
            note TEXT DEFAULT '', ts TEXT, day TEXT, undone INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS daily_summaries (
            date TEXT, item TEXT, day_of_week INTEGER, is_weekend INTEGER,
            total_demand REAL, PRIMARY KEY (date, item));
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
        """)


def get_setting(key, default=None):
    with db() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def set_setting(key, value):
    with db() as c:
        c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, value))


BASE_CATALOG = [
    ("Milk", "Dairy", 18, "packets", 40), ("Bread", "Bakery", 25, "loaves", 20),
    ("Eggs", "Dairy", 60, "trays", 30), ("Curd", "Dairy", 12, "pouches", 15),
    ("Paneer", "Dairy", 8, "packs", 10), ("Sugar", "Staples", 24, "kg", 25),
    ("Toor Dal", "Pulses", 35, "kg", 20), ("Moong Dal", "Pulses", 28, "kg", 15),
    ("Basmati Rice", "Grains", 50, "kg", 30), ("Sona Masoori Rice", "Grains", 80, "kg", 40),
    ("Aashirvaad Atta", "Flour", 45, "kg", 25), ("Besan", "Flour", 15, "kg", 10),
    ("Fortune Mustard Oil", "Oils", 16, "liters", 15), ("Sunrich Refined Oil", "Oils", 22, "liters", 20),
    ("Amul Ghee", "Ghee/Oil", 7, "jars", 10), ("Tata Salt", "Spices", 40, "packets", 20),
    ("Turmeric Powder", "Spices", 18, "packets", 10), ("Red Chilli Powder", "Spices", 14, "packets", 10),
    ("Parle-G Biscuits", "Snacks", 65, "packs", 30), ("Good Day Biscuits", "Snacks", 42, "packs", 20),
    ("Red Label Tea", "Beverages", 20, "packs", 15), ("Bru Coffee", "Beverages", 12, "jars", 10),
    ("Maggi Noodles", "Snacks", 55, "packets", 30),
]


def build_catalog():
    rng = random.Random(42)
    cat = list(BASE_CATALOG)
    for p in ["Chana Dal", "Urad Dal Gota", "Urad Dal Chilka", "Masoor Dal", "Rajma Chitra", "Kabuli Chana",
              "Kala Chana", "Green Moong", "Poha Thick", "Poha Thin", "Rava (Sooji)", "Idli Rava", "Maida",
              "Corn Flour", "Ragi Flour", "Jowar Flour", "Bajra Flour", "Brown Rice", "Kolam Rice", "Jeera Rice"]:
        cat.append((f"{p} 1kg", "Pulses" if ("Dal" in p or "Chana" in p) else "Grains", rng.randint(15, 60), "kg", 10))
    for s in ["Jeera (Cumin)", "Mustard Seeds (Rai)", "Dhaniya Seeds", "Dhaniya Powder", "Garam Masala",
              "Sambar Powder", "Rasam Masala", "Biryani Masala", "Chicken Masala", "Chaat Masala", "Kasuri Methi",
              "Black Pepper", "Cloves (Laung)", "Cardamom (Elaichi)", "Cinnamon (Dalchini)", "Hing (Asafoetida)",
              "Amchur Powder", "Kashmiri Mirch", "Black Salt"]:
        cat.append((f"{s} 100g", "Spices", rng.randint(10, 40), "packets", 8))
    for o in ["Sunflower Oil 1L", "Groundnut Oil 1L", "Sesame Oil 500ml", "Coconut Oil 500ml", "Rice Bran Oil 1L",
              "Cow Ghee 500ml", "Buffalo Ghee 500ml", "Olive Oil 500ml", "Vanaspati Dalda 1L"]:
        for b in ["Fortune", "Dhara", "Patanjali"]:
            cat.append((f"{b} {o}", "Oils", rng.randint(8, 30), "liters" if "1L" in o else "bottles", 5))
    for sn in ["Marie Gold", "Bourbon", "Hide & Seek", "Monaco", "Krackjack", "Oreo Original", "Dark Fantasy",
               "NutriChoice Digestive", "Kurkure Masala Munch", "Lay's Classic Salted", "Lay's India's Magic Masala",
               "Bingo Mad Angles", "Haldiram Bhujia", "Haldiram Aloo Bhujia", "Haldiram Khatta Meetha",
               "Chana Jor Garam", "Roasted Peanuts"]:
        cat.append((f"{sn} Pack", "Snacks", rng.randint(20, 80), "packs", 15))
    for bv in ["Taj Mahal Tea 250g", "Tata Tea Gold 250g", "Wagh Bakri Tea 250g", "Nescafe Classic 50g",
               "Horlicks 500g", "Bournvita 500g", "Boost 500g", "Rooh Afza 750ml", "Tang Orange 500g"]:
        cat.append((bv, "Beverages", rng.randint(10, 35), "packs", 8))
    for sp in ["Lifebuoy Soap 100g", "Dettol Soap 100g", "Lux Rose Soap", "Dove Cream Bar", "Pears Pure & Gentle",
               "Clinic Plus Shampoo 175ml", "Sunsilk Black Shine 175ml", "Head & Shoulders 180ml",
               "Colgate Strong Teeth 200g", "Close Up Red Hot 150g", "Sensodyne Rapid 80g", "Dettol Antiseptic 250ml",
               "Parachute Coconut Hair Oil 200ml", "Bajaj Almond Drops 200ml"]:
        cat.append((sp, "Personal Care", rng.randint(15, 50), "units", 10))
    for cl in ["Surf Excel Quick Wash 1kg", "Ariel Complete 1kg", "Tide Plus Jasmine 1kg", "Rin Detergent Bar",
               "Vim Dishwash Bar 300g", "Vim Liquid Gel 500ml", "Pril Liquid 425ml", "Harpic Power Plus 500ml",
               "Lizol Floor Cleaner 500ml", "Colin Glass Cleaner 500ml", "GoodKnight Mosquito Refill",
               "All Out Ultra Refill", "Comfort Fabric Conditioner 200ml"]:
        cat.append((cl, "Household", rng.randint(12, 45), "units", 8))
    return cat


def seed_catalog(reset=False):
    """Seed demo data. Only runs on an empty DB unless reset=True (explicitly confirmed in UI)."""
    with db() as c:
        if not reset and c.execute("SELECT COUNT(*) n FROM inventory").fetchone()["n"] > 0:
            return
        for tbl in ("inventory", "daily_summaries", "transactions"):
            c.execute(f"DELETE FROM {tbl}")
        ts = now_ist().isoformat(timespec="seconds")
        c.executemany("INSERT INTO inventory(item,category,current_stock,unit,reorder_level,updated_at) "
                      "VALUES(?,?,?,?,?,?)", [(*row, ts) for row in build_catalog()])
        rng, today, rows = random.Random(7), now_ist().date(), []
        for item, _, _, _, reorder in BASE_CATALOG:   # 28 days of synthetic demo history
            for k in range(28, 0, -1):
                d = today - timedelta(days=k)
                wk = d.weekday() >= 5
                if item == "Milk":
                    v = rng.randint(48, 60) if wk else rng.randint(22, 32)
                else:
                    v = round(max(2, reorder // 3) * (1.5 if wk else 1) * rng.uniform(0.8, 1.2))
                rows.append((d.isoformat(), item, d.weekday(), int(wk), v))
        c.executemany("INSERT OR REPLACE INTO daily_summaries VALUES(?,?,?,?,?)", rows)


def catalog_names():
    with db() as c:
        return [r["item"] for r in c.execute("SELECT item FROM inventory ORDER BY item")]


def data_version():
    with db() as c:
        r = c.execute("SELECT COUNT(*) n, COALESCE(MAX(id),0) m FROM transactions").fetchone()
    return f"{now_ist().date()}-{r['n']}-{r['m']}"


# ------------------------------------------------------------ TRANSACTIONS
def _refresh_summary(conn, day: str):
    conn.execute("DELETE FROM daily_summaries WHERE date=?", (day,))
    d = date.fromisoformat(day)
    for r in conn.execute("SELECT item, SUM(applied_qty) q FROM transactions "
                          "WHERE day=? AND action='STOCK_OUT' AND undone=0 GROUP BY item", (day,)).fetchall():
        conn.execute("INSERT INTO daily_summaries VALUES(?,?,?,?,?)",
                     (day, r["item"], d.weekday(), int(d.weekday() >= 5), r["q"]))


def apply_transaction(intent, items, raw_text, request_id):
    """Idempotent: returns None if this request_id was already committed."""
    ts = now_ist()
    results = []
    try:
        with db() as c:
            if c.execute("SELECT 1 FROM transactions WHERE request_id=?", (f"{request_id}:0",)).fetchone():
                return None
            for i, it in enumerate(items):
                row = c.execute("SELECT current_stock, unit FROM inventory WHERE item=?", (it["item"],)).fetchone()
                if not row:
                    continue
                qty, stock = float(it["qty"]), float(row["current_stock"])
                if qty <= 0:
                    continue
                applied = qty if intent == "STOCK_IN" else min(qty, stock)
                new = stock + applied if intent == "STOCK_IN" else stock - applied
                note = "" if applied == qty else f"oversold: only {stock:g} in stock"
                c.execute("INSERT INTO transactions(request_id,raw_text,item,action,qty,applied_qty,note,ts,day) "
                          "VALUES(?,?,?,?,?,?,?,?,?)",
                          (f"{request_id}:{i}", raw_text, it["item"], intent, qty, applied, note,
                           ts.isoformat(timespec="seconds"), ts.date().isoformat()))
                c.execute("UPDATE inventory SET current_stock=?, updated_at=? WHERE item=?",
                          (new, ts.isoformat(timespec="seconds"), it["item"]))
                results.append(dict(item=it["item"], qty=qty, applied=applied, balance=new,
                                    unit=row["unit"], oversold=applied < qty, action=intent))
            if intent == "STOCK_OUT":
                _refresh_summary(c, ts.date().isoformat())
    except sqlite3.IntegrityError:
        return None
    return results


def check_stock(items):
    out = []
    with db() as c:
        for it in items:
            r = c.execute("SELECT current_stock, unit FROM inventory WHERE item=?", (it["item"],)).fetchone()
            if r:
                out.append(dict(item=it["item"], balance=r["current_stock"], unit=r["unit"]))
    return out


def undo_last():
    """Reverse the most recent (multi-item) transaction."""
    with db() as c:
        last = c.execute("SELECT request_id FROM transactions WHERE undone=0 ORDER BY id DESC LIMIT 1").fetchone()
        if not last:
            return None
        rid = last["request_id"].split(":")[0]
        rows = c.execute("SELECT * FROM transactions WHERE request_id LIKE ? AND undone=0", (rid + ":%",)).fetchall()
        for r in rows:
            delta = -r["applied_qty"] if r["action"] == "STOCK_IN" else r["applied_qty"]
            c.execute("UPDATE inventory SET current_stock=current_stock+?, updated_at=? WHERE item=?",
                      (delta, now_ist().isoformat(timespec="seconds"), r["item"]))
            c.execute("UPDATE transactions SET undone=1 WHERE id=?", (r["id"],))
        for day in {r["day"] for r in rows}:
            _refresh_summary(c, day)
        return [r["item"] for r in rows]


# ------------------------------------------------------------------ PARSER
IN_WORDS = ["aaya", "aayi", "aaye", "receive", "received", "truck", "restock", "bought", "laaye", "add", "added",
            "loaded", "arrived", "vachindi", "vachayi", "దిగుమతి", "వచ్చింది", "లోడ్", "వచ్చాయి",
            "vandhadhu", "varavu", "வந்தது", "வரவு", "ஏற்றப்பட்டது", "banthu", "thandidhe", "ಬಂತು", "ದಾಸ್ತಾನು",
            "elo", "ashche", "এলো", "আসলো", "aala", "aale", "आले", "आला", "aavyu", "aavya", "આવ્યું", "આવ્યા",
            "vannu", "kayari", "വന്നു", "കയറ്റി", "pahuncha", "ਆਇਆ", "ਪਹੁੰਚਿਆ", "आया", "आई", "आये", "मंगवाया"]
CHECK_WORDS = ["kitna", "kitni", "kitne", "how many", "how much", "bacha", "bachi", "left", "balance", "check",
               "enni", "unnayi", "ఎన్ని", "ఉన్నాయి", "మిగిలి", "స్టాక్", "evvalavu", "irukku", "எவ்வளவு", "இருக்கிறது",
               "eshtu", "ide", "ಎಷ್ಟು", "ಇದೆ", "koto", "ache", "কত", "আছে", "kiti", "ahe", "किती", "आहे",
               "ketlu", "che", "કેટલું", "છે", "ethra", "undu", "എത്ര", "ഉണ്ട്", "kinna", "haye", "ਕਿੰਨਾ", "ਹੈ",
               "कितना", "कितनी", "कितने", "बचा", "बची"]
SMALL_UNITS = {"g", "gm", "gms", "gram", "grams", "ml", "గ్రాములు", "గ్రాము", "గ్రాం", "ग्राम", "கிராம்", "ಗ್ರಾಂ"}

NUM_WORDS = {}


def _add(v, *words):
    for w in words:
        NUM_WORDS[w] = v


_add(0.5, "half", "aadha", "adha", "aadhi", "అర", "आधा", "आधी")
_add(1.5, "dedh", "डेढ़", "డెబ్భై")  # last is placeholder-free: remove if unwanted
NUM_WORDS.pop("డెబ్భై", None)
_add(2.5, "dhai", "dhaai", "ढाई")
_add(1, "one", "ek", "ఒకటి", "ఒక", "ஒன்று", "ஒரு", "ಒಂದು", "एक", "ondu", "onnu", "ഒന്ന്", "এক", "ਇੱਕ", "એક")
_add(2, "two", "do", "రెండు", "இரண்டு", "ಎರಡು", "दो", "eradu", "randu", "രണ്ട്", "দুই", "ਦੋ", "બે")
_add(3, "three", "teen", "మూడు", "மூன்று", "ಮೂರು", "तीन", "mooru", "മൂന്ന്", "তিন", "ਤਿੰਨ", "ત્રણ")
_add(4, "four", "char", "chaar", "నాలుగు", "நான்கு", "ನಾಲ್ಕು", "चार", "നാല്", "চার", "ਚਾਰ", "ચાર")
_add(5, "five", "paanch", "panch", "ఐదు", "ஐந்து", "ಐದು", "पाँच", "पांच", "അഞ്ച്", "পাঁচ", "ਪੰਜ", "પાંચ")
_add(6, "six", "ఆరు", "ஆறு", "ಆರು", "छह", "छः", "ആറ്", "ছয়")
_add(7, "seven", "saat", "ఏడు", "ஏழு", "ಏಳು", "सात", "ഏഴ്", "সাত")
_add(8, "eight", "aath", "ఎనిమిది", "எட்டு", "ಎಂಟು", "आठ", "എട്ട്", "আট")
_add(9, "nine", "nau", "తొమ్మిది", "ஒன்பது", "ಒಂಬತ್ತು", "नौ", "ഒമ്പത്", "নয়")
_add(10, "ten", "das", "పది", "பத்து", "ಹತ್ತು", "दस", "പത്ത്", "দশ")
_add(20, "twenty", "bees", "ఇరవై", "இருபது", "ಇಪ್ಪತ್ತು", "बीस", "ഇരുപത്", "কুড়ি")
_add(25, "pachees", "पच्चीस", "ఇరవై ఐదు")
_add(50, "fifty", "pachas", "యాభై", "ஐம்பது", "ಐವತ್ತು", "पचास")
_add(100, "hundred", "sau", "వంద", "நூறு", "ನೂರು", "सौ")
NUM_WORDS.pop("ఇరవై ఐదు", None)

EXTRA_ALIASES = {
    "Milk": ["doodh", "dudh", "paalu", "paal", "palu", "haalu", "paalu"],
    "Sugar": ["cheeni", "chini", "panchadara", "sakkare", "shakkar", "sakhar", "khand", "chakkara"],
    "Bread": ["pav", "pao", "double roti"],
    "Eggs": ["egg", "anda", "ande", "guddu", "muttai", "dim", "mottai"],
    "Curd": ["dahi", "perugu", "thayir", "mosaru", "yogurt"],
    "Paneer": ["panir"],
    "Toor Dal": ["toor", "tur dal", "arhar", "kandipappu", "kandi pappu"],
    "Moong Dal": ["moong", "pesara pappu"],
    "Basmati Rice": ["basmati"],
    "Sona Masoori Rice": ["rice", "chawal", "biyyam", "biyyamu", "arisi", "akki"],
    "Aashirvaad Atta": ["atta", "aata", "gehu", "godhuma pindi", "wheat flour"],
    "Besan": ["sanaga pindi", "gram flour"],
    "Fortune Mustard Oil": ["sarson", "mustard oil"],
    "Sunrich Refined Oil": ["oil", "tel", "tail", "nune", "cooking oil", "ennai", "enne"],
    "Amul Ghee": ["ghee", "neyyi", "tuppa", "nei"],
    "Tata Salt": ["salt", "namak", "uppu", "nimak"],
    "Red Label Tea": ["tea", "chai", "chai patti"],
    "Bru Coffee": ["coffee"],
    "Maggi Noodles": ["maggi", "noodles"],
}


def _norm(text: str) -> str:
    t = text.lower()
    return "".join(str(unicodedata.decimal(ch)) if ch.isdecimal() else ch for ch in t)


def _has(t: str, kw: str) -> bool:
    if kw.isascii():
        return re.search(rf"(?<![a-z]){re.escape(kw)}(?![a-z])", t) is not None
    return kw in t


def detect_intent(t: str) -> str:
    if any(_has(t, k) for k in IN_WORDS):
        return "STOCK_IN"
    if "?" in t or any(_has(t, k) for k in CHECK_WORDS):
        return "CHECK_STOCK"
    return "STOCK_OUT"


@lru_cache(maxsize=4)
def _alias_patterns(names: tuple):
    alias = {}

    def add(a, item):
        a = _norm(a).strip()
        if len(a) < 2 or (a.isascii() and len(a) < 3):
            return
        alias.setdefault(a, item)

    for n in names:
        add(n, n)
        add(re.sub(r"\s*\d+\s*(kg|g|l|ml)\b", "", n.lower()), n)
    for key, langs in ITEM_TRANSLATIONS.items():
        if key not in names:
            continue
        for v in langs.values():
            for part in re.split(r"[/()]", v):
                add(part, key)
        for a in EXTRA_ALIASES.get(key, []):
            add(a, key)
    pats = []
    for a, item in alias.items():
        p = rf"(?<![a-z]){re.escape(a)}(?![a-z])" if a.isascii() else re.escape(a)
        pats.append((re.compile(p), item, len(a)))
    return sorted(pats, key=lambda x: -x[2])


def find_items(t: str, names):
    taken, out = [], []
    for pat, item, _ in _alias_patterns(tuple(names)):
        for m in pat.finditer(t):
            s, e = m.span()
            if any(s < te and ts < e for ts, te in taken):
                continue
            taken.append((s, e))
            out.append((s, e, item))
    out.sort()
    return out


def _numbers(t: str):
    toks = list(re.finditer(r"\d+(?:\.\d+)?|[^\s,;:!?।\d]+", t))
    out = []
    for i, m in enumerate(toks):
        w = m.group().strip(".")
        if re.fullmatch(r"\d+(?:\.\d+)?", w):
            val = float(w)
        elif w in NUM_WORDS:
            val = float(NUM_WORDS[w])
        else:
            continue
        nxt = toks[i + 1].group().strip(".") if i + 1 < len(toks) else ""
        if nxt in SMALL_UNITS:
            val /= 1000
        out.append((m.start(), m.end(), val))
    return out


def parse_rules(text: str, names):
    t = _norm(text)
    spans = find_items(t, names)
    if not spans:
        return {"intent": "UNKNOWN", "items": [], "engine": "Rule-Engine"}
    intent = detect_intent(t)
    items, seen = [], set()
    nums, used = _numbers(t), set()
    for s, e, item in spans:
        if item in seen:
            continue
        seen.add(item)
        if intent == "CHECK_STOCK":
            items.append({"item": item, "qty": 0, "assumed": False})
            continue
        best = None
        for j, (ns, ne, v) in enumerate(nums):
            if j in used or (ns >= s and ne <= e):
                continue
            d = s - ne if ne <= s else ns - e
            key = (d, 0 if ne <= s else 1)
            if best is None or key < best[0]:
                best = (key, j, v)
        if best and best[0][0] <= 40:
            used.add(best[1])
            items.append({"item": item, "qty": best[2], "assumed": False})
        else:
            items.append({"item": item, "qty": 1, "assumed": True})
    return {"intent": intent, "items": items, "engine": "Rule-Engine"}


def parse_with_llm(text, names, hint_names=()):
    prompt = (
        "You are a kirana (grocery) shop assistant. The shopkeeper spoke in an Indian language or Hinglish.\n"
        f"Common items: {', '.join(hint_names)}\n"
        'Return ONLY JSON: {"intent":"STOCK_IN|STOCK_OUT|CHECK_STOCK|UNKNOWN",'
        '"items":[{"item":"<English item name>","qty":<number>}]}\n'
        "STOCK_OUT = sold, STOCK_IN = new stock arrived, CHECK_STOCK = asking how much is left.\n"
        f"Utterance: {text}")
    try:
        r = requests.post(OLLAMA_URL, json={"model": OLLAMA_MODEL, "prompt": prompt, "format": "json",
                                            "stream": False, "options": {"temperature": 0}}, timeout=8)
        data = json.loads(r.json()["response"])
        intent = data.get("intent")
        if intent not in ("STOCK_IN", "STOCK_OUT", "CHECK_STOCK"):
            return None
        lower = {n.lower(): n for n in names}
        items = []
        for it in data.get("items", []):
            raw = str(it.get("item", "")).lower().strip()
            name = lower.get(raw) or (lambda m: lower[m[0]] if m else None)(get_close_matches(raw, lower, 1, 0.7))
            qty = float(it.get("qty") or 1)
            if name and (qty > 0 or intent == "CHECK_STOCK") and name not in [i["item"] for i in items]:
                items.append({"item": name, "qty": 0 if intent == "CHECK_STOCK" else qty, "assumed": False})
        return {"intent": intent, "items": items, "engine": "Gemma"} if items else None
    except Exception:
        return None


def parse_input(text, use_llm=False, hint_names=()):
    names = catalog_names()
    res = parse_rules(text, names)
    if res["intent"] == "UNKNOWN" and use_llm:
        res = parse_with_llm(text, names, hint_names) or res
    return res


# ---------------------------------------------------------------- FORECAST
def is_festival(d: date) -> bool:
    return any(abs((d - f).days) <= 1 for f in FESTIVALS)


def _heuristic(s: pd.Series, target: date):
    wk = target.weekday() >= 5
    same = s[(s.index.weekday >= 5) == wk]
    base_s = same if len(same) >= 2 else s
    base = base_s.mean() * (1.15 if is_festival(target) else 1.0)
    return base, float(base_s.std() or 0)


def _tabpfn(s: pd.Series, target: date):
    from tabpfn import TabPFNRegressor
    df = pd.DataFrame({"y": s})
    ix = df.index
    df["dow"], df["wknd"] = ix.weekday, (ix.weekday >= 5).astype(int)
    df["fest"] = [int(is_festival(d.date())) for d in ix]
    df["lag7"] = s.shift(7)
    df["roll7"] = s.shift(2).rolling(7).mean()   # features usable 2 days ahead (history ends yesterday)
    train = df.dropna()
    if len(train) < 14:
        return None
    x_new = pd.DataFrame([{"dow": target.weekday(), "wknd": int(target.weekday() >= 5),
                           "fest": int(is_festival(target)), "lag7": s.iloc[-6], "roll7": s.iloc[-7:].mean()}])
    model = TabPFNRegressor()
    model.fit(train.drop(columns="y"), train["y"])
    return float(model.predict(x_new)[0]), float(s.tail(14).std() or 0)


def forecast_item(conn, item, target: date, use_tabpfn=True):
    yesterday = now_ist().date() - timedelta(days=1)
    df = pd.read_sql_query("SELECT date, total_demand FROM daily_summaries WHERE item=? AND date<=? ORDER BY date",
                           conn, params=(item, yesterday.isoformat()))
    if len(df) < 3:
        return None
    s = pd.Series(df.total_demand.values, index=pd.to_datetime(df.date))
    s = s.reindex(pd.date_range(s.index.min(), pd.Timestamp(yesterday)), fill_value=0.0)  # no-sale days = 0
    if use_tabpfn and len(s) >= 22:
        try:
            r = _tabpfn(s, target)
            if r:
                return max(0.0, r[0]), r[1], "TabPFN"
        except Exception:
            pass
    pred, sd = _heuristic(s, target)
    return max(0.0, pred), sd, "Heuristic"


def compute_alerts(use_tabpfn=True, buffer=0.15):
    target = now_ist().date() + timedelta(days=1)
    alerts = []
    with db() as c:
        rows = c.execute("SELECT item, current_stock, unit FROM inventory "
                         "WHERE item IN (SELECT DISTINCT item FROM daily_summaries)").fetchall()
        for r in rows:
            f = forecast_item(c, r["item"], target, use_tabpfn)
            if not f:
                continue
            pred, sd, engine = f
            pred_i, stock = round(pred), r["current_stock"]
            if pred_i > stock:
                alerts.append(dict(item=r["item"], stock=stock, demand=pred_i, unit=r["unit"], engine=engine,
                                   low=max(0, round(pred - sd)), high=round(pred + sd),
                                   order=math.ceil(pred * (1 + buffer) - stock)))
    return sorted(alerts, key=lambda a: a["demand"] - a["stock"], reverse=True)
