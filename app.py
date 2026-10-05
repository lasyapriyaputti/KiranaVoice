import hashlib
import html
import json
import os
import uuid

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import core
from i18n import TRANSLATIONS
from messages import CHECK, REPEAT, UI, WARN, get_localized_item_name, pick

mic_component = components.declare_component(
    "kirana_mic", path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "mic_component"))

st.set_page_config(page_title="KiranaVoice | Multilingual AI Counter Assistant", page_icon="🏪",
                   layout="wide", initial_sidebar_state="expanded")


@st.cache_resource
def setup():
    core.init_db()
    core.seed_catalog()  # only seeds an empty DB
    return True


setup()

# ------------------------------------------------------------ session state
if "pref_lang" not in st.session_state:
    saved = core.get_setting("pref_lang", "Telugu (తెలుగు)")
    st.session_state["pref_lang"] = saved if saved in TRANSLATIONS else "Telugu (తెలుగు)"
for k, v in {"active_nav": "nav_mic", "transcript_box": "", "parse_cache": None, "receipt": None}.items():
    st.session_state.setdefault(k, v)

lang = st.session_state["pref_lang"]
t = TRANSLATIONS[lang]
ui = lambda key: pick(UI, lang, key)
unit_lbl = lambda u: t["units"].get(u, u)
loc = lambda n: get_localized_item_name(n, lang)
fmt = lambda x: f"{x:g}" if isinstance(x, (int, float)) else x

FLAG_DEFAULTS = {"use_llm": "0", "use_tabpfn": "0", "auto_speak": "1"}   # TabPFN off until set up


def get_flag(k):
    return core.get_setting(k, FLAG_DEFAULTS[k]) == "1"


def save_flag(k):
    core.set_setting(k, "1" if st.session_state[f"w_{k}"] else "0")


ADV = {
    "English": {"title": "🔧 Advanced (owner only)", "use_llm": "AI helper for unclear speech (Gemma)",
                "use_tabpfn": "Smart tomorrow-demand forecast (TabPFN)", "auto_speak": "Read confirmation aloud automatically"},
    "Telugu": {"title": "🔧 అధునాతన (యజమాని కోసం మాత్రమే)", "use_llm": "అర్థం కాని మాటలకు AI సహాయం (Gemma)",
               "use_tabpfn": "రేపటి డిమాండ్ స్మార్ట్ అంచనా (TabPFN)", "auto_speak": "నిర్ధారణను ఆటోమేటిక్‌గా చదివి వినిపించు"},
    "Hindi": {"title": "🔧 एडवांस्ड (सिर्फ़ मालिक के लिए)", "use_llm": "न समझ आने पर AI की मदद (Gemma)",
              "use_tabpfn": "कल की मांग का स्मार्ट अनुमान (TabPFN)", "auto_speak": "पुष्टि अपने आप बोलकर सुनाएँ"},
}


def go_home():
    st.session_state["active_nav"] = "nav_mic"


def speak_button(text: str, label: str, autoplay: bool = False):
    bid = "tts_" + hashlib.md5(text.encode()).hexdigest()[:10]
    auto = "speak();" if autoplay else ""
    components.html(f"""
    <button id="{bid}" style="background:linear-gradient(135deg,#d97706,#b45309);color:#fff;border:none;
      border-radius:20px;padding:7px 18px;font-weight:700;font-size:14px;cursor:pointer;">{html.escape(label)}</button>
    <script>
      function speak() {{
        if (!('speechSynthesis' in window)) return;
        window.speechSynthesis.cancel();
        var u = new SpeechSynthesisUtterance({json.dumps(text)});
        u.lang = '{t["bcp"]}'; u.rate = 0.92; window.speechSynthesis.speak(u);
      }}
      document.getElementById('{bid}').onclick = speak;
      {auto}
    </script>""", height=48)


def back_button():
    st.button(t["back_to_mic"], type="primary", on_click=go_home)


@st.cache_data(ttl=600, show_spinner=False)
def cached_alerts(version: str, use_tabpfn: bool):
    return core.compute_alerts(use_tabpfn)


# ----------------------------------------------------------------- sidebar
with st.sidebar:
    st.title(t["title"])
    st.caption(t["subtitle"])
    st.markdown("---")
    labels = {"nav_mic": t["nav_mic"], "nav_items": t["nav_items"], "nav_ledger": t["nav_ledger"],
              "nav_low": t["nav_low"], "nav_settings": t["nav_settings"]}
    st.radio("Navigation", list(labels), format_func=labels.get, key="active_nav", label_visibility="collapsed")
    st.markdown("---")
    st.caption(f"🟢 **Language:** {lang}")

nav = st.session_state["active_nav"]

# --------------------------------------------------------------- ALL ITEMS
if nav == "nav_items":
    c1, c2 = st.columns([3, 1])
    c1.subheader(t["nav_items"])
    with c2:
        back_button()
    q = st.text_input(t["search_label"]).strip().lower()
    with core.db() as conn:
        df = pd.read_sql_query("SELECT item, category, current_stock, unit, reorder_level "
                               "FROM inventory ORDER BY category, item", conn)
    df["local"] = df["item"].map(loc)
    if q:
        df = df[df["item"].str.lower().str.contains(q, regex=False) | df["local"].str.lower().str.contains(q, regex=False)]
    out = pd.DataFrame({t["col_item"]: df["local"], t["col_category"]: df["category"].map(lambda x: t["categories"].get(x, x)),
                        t["col_stock"]: df["current_stock"].round(2), t["col_unit"]: df["unit"].map(unit_lbl),
                        t["col_reorder"]: df["reorder_level"]})
    st.dataframe(out, hide_index=True, use_container_width=True)

# ------------------------------------------------------------------ LEDGER
elif nav == "nav_ledger":
    c1, c2 = st.columns([3, 1])
    c1.subheader(t["nav_ledger"])
    with c2:
        back_button()
    today = core.now_ist().date().isoformat()
    with core.db() as conn:
        tx = pd.read_sql_query("SELECT ts, item, action, applied_qty, note FROM transactions "
                               "WHERE day=? AND undone=0 ORDER BY id DESC", conn, params=(today,))
    if len(tx):
        out = pd.DataFrame({t["col_time"]: tx["ts"].str[11:16], t["col_item"]: tx["item"].map(loc),
                            t["col_action"]: tx["action"].map(lambda a: t["actions"].get(a, a)),
                            t["col_qty"]: tx["applied_qty"].round(2)})
        st.dataframe(out, hide_index=True, use_container_width=True)
        if st.button(ui("undo_btn")):
            st.success(ui("undo_done") if core.undo_last() else ui("nothing_undo"))
            st.rerun()
    else:
        st.info(ui("no_tx"))

# --------------------------------------------------------------- LOW STOCK
elif nav == "nav_low":
    c1, c2 = st.columns([3, 1])
    c1.subheader(t["nav_low"])
    with c2:
        back_button()
    with core.db() as conn:
        low = pd.read_sql_query("SELECT item, current_stock, unit, reorder_level FROM inventory "
                                "WHERE current_stock <= reorder_level ORDER BY item", conn)
    if len(low):
        out = pd.DataFrame({t["col_item"]: low["item"].map(loc), t["col_stock"]: low["current_stock"].round(2),
                            t["col_unit"]: low["unit"].map(unit_lbl), t["col_reorder"]: low["reorder_level"]})
        st.dataframe(out, hide_index=True, use_container_width=True)
    else:
        st.success(ui("all_safe"))

# ---------------------------------------------------------------- SETTINGS
elif nav == "nav_settings":
    c1, c2 = st.columns([3, 1])
    c1.subheader(t["nav_settings"])
    with c2:
        back_button()
    st.markdown("---")
    st.write(f"### {t['lang_select_label']}")
    langs = list(TRANSLATIONS)
    choice = st.selectbox("Language", langs, index=langs.index(lang), label_visibility="collapsed")
    if st.button(t["lang_save_btn"], type="primary", use_container_width=True):
        st.session_state["pref_lang"] = choice
        core.set_setting("pref_lang", choice)   # persisted across restarts
        st.rerun()
    st.markdown("---")
    with st.expander(pick(ADV, lang, "title")):
        for fk in ("use_llm", "use_tabpfn", "auto_speak"):
            st.toggle(pick(ADV, lang, fk), value=get_flag(fk), key=f"w_{fk}", on_change=save_flag, args=(fk,))
    st.markdown("---")
    st.warning("⚠️ Reset deletes ALL stock, ledger and history and loads demo data.")
    sure = st.checkbox("I understand, erase everything")
    if st.button(t["reset_demo_btn"], use_container_width=True, disabled=not sure):
        core.seed_catalog(reset=True)
        cached_alerts.clear()
        st.success(t["reset_success"])

# ------------------------------------------------------------ VOICE COUNTER
else:
    # 1. Proactive morning alerts (all items with history, not just Milk)
    alerts = cached_alerts(core.data_version(), get_flag("use_tabpfn"))
    for a in alerts[:3]:
        text = pick(WARN, lang).format(item=loc(a["item"]), demand=a["demand"], stock=fmt(round(a["stock"], 1)),
                                       order=a["order"], unit=unit_lbl(a["unit"]))
        w1, w2 = st.columns([4, 1])
        w1.markdown(f"""<div style="background:#fef3c7;border:2px solid #f59e0b;border-radius:14px;padding:12px 16px;margin-bottom:8px;">
            <span style="background:#f59e0b;color:#fff;padding:3px 8px;border-radius:6px;font-weight:bold;font-size:12px;">{t['urgent_badge']}</span>
            <span style="font-size:11px;color:#92400e;margin-left:8px;">{a['engine']} · {a['low']}–{a['high']}</span>
            <div style="font-size:16px;font-weight:bold;color:#78350f;margin-top:6px;">{html.escape(text)}</div></div>""",
                     unsafe_allow_html=True)
        with w2:
            speak_button(text, t["listen_btn"])

    # 2. Mic: returns text straight to Python (no page reload, session state survives)
    mic = mic_component(lang=t["bcp"], label_text=t["mic_btn_text"], status_text=t["mic_status"],
                        key=f"mic_{t['bcp']}", default=None)
    if mic and mic.get("id") != st.session_state.get("last_mic_id"):
        st.session_state["last_mic_id"] = mic["id"]
        st.session_state["transcript_box"] = mic["text"]
        st.session_state["receipt"] = None
    spoken = st.text_input("Spoken Input", key="transcript_box", placeholder=t["input_placeholder"],
                           label_visibility="collapsed").strip()

    def reset_input():
        st.session_state["transcript_box"] = ""
        st.session_state["parse_cache"] = None

    def confirm(intent, items, raw, rid, keys):
        final = [{**it, "qty": st.session_state.get(k, it["qty"])} for it, k in zip(items, keys)]
        st.session_state["receipt"] = core.apply_transaction(intent, final, raw, rid) or []
        cached_alerts.clear()
        reset_input()

    # 3. Parse once per utterance (cached so edits don't re-call the LLM)
    if spoken:
        ck = (spoken, lang)
        pc = st.session_state["parse_cache"]
        if not pc or pc["key"] != ck:
            names = list(__import__("i18n").ITEM_TRANSLATIONS)
            pc = {"key": ck, "rid": uuid.uuid4().hex,
                  "parsed": core.parse_input(spoken, get_flag("use_llm"), names)}
            st.session_state["parse_cache"] = pc
        parsed, intent, items = pc["parsed"], pc["parsed"]["intent"], pc["parsed"]["items"]

        if intent == "UNKNOWN" or not items:
            st.error(ui("not_understood"))   # never guess an item
            st.button(t["cancel_btn"], on_click=reset_input)

        elif intent == "CHECK_STOCK":        # read-only: answer immediately, no confirm needed
            lines = [pick(CHECK, lang).format(item=loc(r["item"]), stock=fmt(round(r["balance"], 2)), unit=unit_lbl(r["unit"]))
                     for r in core.check_stock(items)]
            msg = " ".join(lines)
            st.markdown(f"""<div style="background:#eff6ff;border:2px solid #3b82f6;border-radius:14px;padding:18px;margin-top:12px;">
                <div style="font-size:20px;font-weight:bold;color:#0f172a;">{html.escape(msg)}</div></div>""",
                        unsafe_allow_html=True)
            speak_button(msg, t["review_audio_btn"], autoplay=get_flag("auto_speak"))
            st.button(t["back_to_mic"], on_click=reset_input)

        else:
            # editable quantities
            keys, parts = [], []
            st.markdown(f"**{t['review_title']}**")
            for i, it in enumerate(items):
                k = f"qty_{pc['rid']}_{i}"
                keys.append(k)
                c_a, c_b = st.columns([3, 1])
                c_a.markdown(f"### {loc(it['item'])}")
                val = c_b.number_input(t["col_qty"], min_value=0.0, value=float(it["qty"]), step=1.0, key=k,
                                       label_visibility="collapsed")
                parts.append(f"{fmt(val)} {loc(it['item'])}")
                if it.get("assumed"):
                    st.warning(ui("assumed"))
            if intent == "STOCK_OUT":
                with core.db() as conn:
                    for it, k in zip(items, keys):
                        r = conn.execute("SELECT current_stock FROM inventory WHERE item=?", (it["item"],)).fetchone()
                        if r and st.session_state.get(k, it["qty"]) > r["current_stock"]:
                            st.warning(f"{loc(it['item'])}: {ui('oversold')} ({fmt(round(r['current_stock'], 2))})")
            repeat = pick(REPEAT, lang, intent).format(items=", ".join(parts))
            st.markdown(f"""<div style="background:#eff6ff;border:2px solid #3b82f6;border-radius:14px;padding:18px;margin-top:8px;">
                <div style="font-size:20px;font-weight:bold;color:#0f172a;">"{html.escape(repeat)}"</div></div>""",
                        unsafe_allow_html=True)
            speak_button(repeat, t["review_audio_btn"], autoplay=get_flag("auto_speak"))
            b1, b2 = st.columns([2, 1])
            b1.button(t["confirm_btn"], type="primary", use_container_width=True, on_click=confirm,
                      args=(intent, items, spoken, pc["rid"], keys))
            b2.button(t["cancel_btn"], use_container_width=True, on_click=reset_input)

    # 4. Receipt
    rc = st.session_state["receipt"]
    if rc is not None and not spoken:
        st.markdown("---")
        lines = [f"{t['actions'].get(r['action'], r['action'])}: {fmt(r['applied'])} {loc(r['item'])}. "
                 f"{ui('balance')}: {fmt(round(r['balance'], 2))} {unit_lbl(r['unit'])}." for r in rc]
        if not lines:
            st.info("Already saved.")
        else:
            st.markdown(f"""<div style="background:#fff;border:1px solid #cbd5e1;border-radius:12px;padding:16px;">
                <div style="font-size:12px;font-weight:bold;color:#64748b;">{t['saved_receipt']}</div>
                <div style="color:#059669;font-weight:bold;font-size:15px;margin-top:6px;">{html.escape(' | '.join(lines))}</div></div>""",
                        unsafe_allow_html=True)
            for r in rc:
                if r["oversold"]:
                    st.warning(f"{loc(r['item'])}: {ui('oversold')}")
            speak_button(" ".join(lines), "🔊 " + t["listen_btn"].replace("🔊", "").strip())
            if st.button(ui("undo_btn")):
                st.success(ui("undo_done") if core.undo_last() else ui("nothing_undo"))
                st.session_state["receipt"] = None
                cached_alerts.clear()
                st.rerun()