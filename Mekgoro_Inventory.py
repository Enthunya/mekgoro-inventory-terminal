import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --------------------------------------------------
# Page config – mobile friendly
# --------------------------------------------------
st.set_page_config(
    page_title="Mekgoro Stock",
    page_icon="logo.png",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --------------------------------------------------
# Styling
# --------------------------------------------------
st.markdown("""
<style>
.stApp { background-color: #f9f9f9; padding: 10px; }
h1, h2 { color: #006400; }

.stButton > button {
    width: 100%;
    height: 52px;
    font-size: 18px;
    margin: 10px 0;
}

.stTextInput input, .stNumberInput input {
    font-size: 18px;
    padding: 12px;
}

.success { background: #e8f5e9; padding: 16px; border-radius: 8px; margin: 12px 0; }
.warning { background: #fff3cd; padding: 16px; border-radius: 8px; margin: 12px 0; }
.error   { background: #ffebee;  padding: 16px; border-radius: 8px; margin: 12px 0; }

.stock-number {
    font-size: 42px;
    font-weight: bold;
    color: #006400;
    text-align: center;
    margin: 20px 0;
}
</style>
""", unsafe_allow_html=True)

# --------------------------------------------------
# Database
# --------------------------------------------------
db = sqlite3.connect("mekgoro_stock.db", check_same_thread=False)

def init_db():
    db.execute("""
        CREATE TABLE IF NOT EXISTS stock (
            item TEXT PRIMARY KEY,
            qty INTEGER DEFAULT 0,
            last_updated TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            item TEXT,
            qty INTEGER,
            party TEXT,
            ref TEXT,
            user TEXT,
            ts TEXT
        )
    """)
    db.commit()

init_db()

# --------------------------------------------------
# Helpers
# --------------------------------------------------
def get_qty(item):
    row = pd.read_sql(
        "SELECT qty FROM stock WHERE item = ?",
        db, params=(item.strip(),)
    )
    return int(row.iloc[0]["qty"]) if not row.empty else 0

def change_stock(item, delta, typ, party="", ref=""):
    item = item.strip()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    user = st.session_state.get("user", "Unknown")

    db.execute("""
        INSERT INTO stock (item, qty, last_updated)
        VALUES (?, ?, ?)
        ON CONFLICT(item)
        DO UPDATE SET qty = qty + ?, last_updated = ?
    """, (item, max(delta, 0), now, delta, now))

    db.execute("""
        INSERT INTO log (type, item, qty, party, ref, user, ts)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (typ, item, delta, party, ref, user, now))

    db.commit()

# --------------------------------------------------
# Login
# --------------------------------------------------
if "user" not in st.session_state:
    st.image("logo.png", width=220)
    st.markdown("<h3 style='text-align:center; color:#006400;'>MEKGORO CONSULTING</h3>", unsafe_allow_html=True)
    st.title("Login")

    users = ["Ndule", "Tshepo", "Biino", "Anthony", "Mike"]
    user = st.selectbox("Who is using?", users)

    if st.button("Enter", type="primary"):
        st.session_state.user = user
        st.rerun()

    st.stop()

# --------------------------------------------------
# Header
# --------------------------------------------------
st.image("logo.png", width=220)
st.markdown("<h3 style='text-align:center; color:#006400;'>MEKGORO CONSULTING</h3>", unsafe_allow_html=True)
st.title(f"Stock – {st.session_state.user}")

tab_stock, tab_receive, tab_out, tab_log = st.tabs(
    ["📊 Stock", "📥 Receive", "📤 Out", "📋 Log"]
)

# --------------------------------------------------
# Stock tab
# --------------------------------------------------
with tab_stock:
    df = pd.read_sql("SELECT item, qty, last_updated FROM stock ORDER BY item", db)
    if df.empty:
        st.info("No items yet – start receiving stock.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

# --------------------------------------------------
# Receive tab
# --------------------------------------------------
with tab_receive:
    supplier = st.text_input("Supplier")
    ref = st.text_input("Invoice / Ref")
    item = st.text_input("Item")
    qty = st.number_input("Qty Received", min_value=1, step=1)

    if st.button("Receive", type="primary"):
        if not item.strip():
            st.markdown('<div class="warning">Enter item name</div>', unsafe_allow_html=True)
        else:
            change_stock(item, qty, "receive", supplier, ref)
            st.markdown(
                f'<div class="success">Added {qty} × <b>{item}</b></div>',
                unsafe_allow_html=True
            )
            st.rerun()

# --------------------------------------------------
# Out tab
# --------------------------------------------------
with tab_out:
    item = st.text_input("Item")
    current = get_qty(item) if item.strip() else 0

    st.markdown(f'<div class="stock-number">{current}</div>', unsafe_allow_html=True)
    st.caption("In stock")

    qty = st.number_input("Qty Leaving", min_value=1, step=1)
    client = st.text_input("Client / Site")
    ref = st.text_input("PO / Ref")

    if st.button("Confirm Out", type="primary"):
        if qty > current:
            st.markdown(
                f'<div class="error">Not enough stock ({current} available)</div>',
                unsafe_allow_html=True
            )
        else:
            change_stock(item, -qty, "out", client, ref)
            st.markdown(
                f'<div class="success">Removed {qty} × <b>{item}</b></div>',
                unsafe_allow_html=True
            )
            st.rerun()

# --------------------------------------------------
# Log tab
# --------------------------------------------------
with tab_log:
    df = pd.read_sql("""
        SELECT ts, type, item, qty, party, ref, user
        FROM log
        ORDER BY ts DESC
        LIMIT 50
    """, db)

    if df.empty:
        st.info("No movements yet.")
    else:
        df["qty"] = df["qty"].apply(lambda x: f"+{x}" if x > 0 else str(x))
        st.dataframe(df, use_container_width=True, hide_index=True)

# --------------------------------------------------
# Sidebar
# --------------------------------------------------
with st.sidebar:
    st.markdown("**MEKGORO CONSULTING**")
    st.write(f"User: **{st.session_state.user}**")
    if st.button("Logout"):
        st.session_state.clear()
        st.rerun()
    st.caption(datetime.now().strftime("%Y-%m-%d %H:%M"))
