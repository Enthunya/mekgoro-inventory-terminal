import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# Page config – mobile friendly
st.set_page_config(
    page_title="Mekgoro Stock",
    page_icon="logo.png",
    layout="wide",
    initial_sidebar_state="collapsed"  # good for phones
)

# Basic styling – large buttons, readable on small screens
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
    .stock-number { font-size: 42px; font-weight: bold; color: #006400; text-align: center; margin: 20px 0; }
    </style>
""", unsafe_allow_html=True)

# Database – local file
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
            type TEXT,          -- 'receive' or 'out'
            item TEXT,
            qty INTEGER,
            party TEXT,         -- supplier or client
            ref TEXT,
            user TEXT,
            ts TEXT
        )
    """)
    db.commit()

init_db()

# Helpers
def get_qty(item):
    row = pd.read_sql("SELECT qty FROM stock WHERE item = ?", db, params=(item.strip(),))
    return row.iloc[0]['qty'] if not row.empty else 0

def change_stock(item, delta, typ, party="", ref=""):
    item = item.strip()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    user = st.session_state.get("user", "Unknown")

    db.execute("""
        INSERT OR REPLACE INTO stock (item, qty, last_updated)
        VALUES (?, COALESCE((SELECT qty FROM stock WHERE item=?), 0) + ?, ?)
    """, (item, item, delta, now))

    db.execute("""
        INSERT INTO log (type, item, qty, party, ref, user, ts)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (typ, item, delta, party, ref, user, now))

    db.commit()

def known_items():
    df = pd.read_sql("SELECT DISTINCT item FROM stock ORDER BY item", db)
    return df['item'].tolist() if not df.empty else []

# Login
if "user" not in st.session_state:
    st.image("logo.png", width=220)
    st.markdown("<h3 style='text-align:center; color:#006400;'>MEKGORO CONSULTING</h3>", unsafe_allow_html=True)
    st.title("Login")

    users = ["Ndule", "Tshepo", "Biino", "Anthony", "Mike"]
    u = st.selectbox("Who is using?", users, key="login_user")
    if st.button("Enter", type="primary", use_container_width=True):
        st.session_state.user = u
        st.rerun()
    st.stop()

# Header on every page
st.image("logo.png", width=220)
st.markdown("<h3 style='text-align:center; color:#006400;'>MEKGORO CONSULTING</h3>", unsafe_allow_html=True)
st.title(f"Stock – {st.session_state.user}")

tab_stock, tab_receive, tab_out, tab_log = st.tabs(
    ["📊 Stock", "📥 Receive", "📤 Out", "📋 Log"]
)

# Stock tab
with tab_stock:
    st.subheader("Current Stock")
    df = pd.read_sql("SELECT item, qty, last_updated FROM stock ORDER BY item", db)
    if df.empty:
        st.info("No items yet – start receiving")
    else:
        def color(v):
            if v <= 0: return 'color:red; font-weight:bold;'
            if v <= 10: return 'color:#d97706; font-weight:bold;'
            return ''
        st.dataframe(
            df.style.format({"qty": "{:,}"}).map(color, subset=["qty"]),
            use_container_width=True,
            hide_index=True
        )

# Receive tab
with tab_receive:
    st.subheader("Receive Goods")
    supplier = st.text_input("Supplier", key="rec_sup")
    ref = st.text_input("Invoice / Ref", key="rec_ref")
    item = st.text_input("Item", placeholder="e.g. Nitrile Gloves Large Blue", key="rec_item")
    qty = st.number_input("Qty Received", min_value=0, step=1, key="rec_qty")

    if st.button("Receive", type="primary", use_container_width=True):
        item = item.strip()
        if not item:
            st.markdown('<div class="warning-msg">Enter item name</div>', unsafe_allow_html=True)
        elif qty <= 0:
            st.markdown('<div class="warning-msg">Qty > 0</div>', unsafe_allow_html=True)
        else:
            change_stock(item, qty, "receive", ref, supplier)
            st.markdown(f"""
                <div class="success-msg">
                Added {qty:,} × <b>{item}</b> from {supplier or 'Unknown'}<br>
                Ref: {ref or '—'}
                </div>
            """, unsafe_allow_html=True)
            st.rerun()

# Out tab
with tab_out:
    st.subheader("Goods Out")
    item = st.text_input("Item", placeholder="e.g. Nitrile Gloves Large Blue", key="out_item")
    
    curr = get_current_stock(item) if item.strip() else 0
    st.markdown(f'<div class="stock-big">{curr:,}</div>', unsafe_allow_html=True)
    st.markdown('<div class="metric-label">In stock right now</div>', unsafe_allow_html=True)
    
    qty = st.number_input("Qty Leaving", min_value=0, step=1, key="out_qty")
    client = st.text_input("Client / Site", key="out_client")
    ref = st.text_input("PO / Ref", key="out_ref")

    if st.button("Confirm Out", type="primary", use_container_width=True):
        item = item.strip()
        if not item:
            st.markdown('<div class="warning-msg">Enter item</div>', unsafe_allow_html=True)
        elif qty <= 0:
            st.markdown('<div class="warning-msg">Qty > 0</div>', unsafe_allow_html=True)
        elif curr < qty:
            st.markdown(f"""
                <div class="error-msg">
                Not enough! Only {curr:,} in stock.
                </div>
            """, unsafe_allow_html=True)
        else:
            change_stock(item, -qty, "out", ref, client)
            st.markdown(f"""
                <div class="success-msg">
                Removed {qty:,} × <b>{item}</b> for {client or 'Unknown'}<br>
                Ref: {ref or '—'}
                </div>
            """, unsafe_allow_html=True)
            st.rerun()

# History tab
with tab_log:
    st.subheader("History")
    df = pd.read_sql("""
        SELECT ts, type, item_name, quantity, party, ref, user
        FROM movements ORDER BY ts DESC LIMIT 50
    """, db)
    if df.empty:
        st.info("No movements yet.")
    else:
        df['type'] = df['type'].replace({'receive': 'IN', 'out': 'OUT'})
        df['quantity'] = df['quantity'].apply(lambda x: f"+{x:,}" if x > 0 else f"{x:,}")
        st.dataframe(df, use_container_width=True, hide_index=True)

# Sidebar
with st.sidebar:
    st.markdown("**MEKGORO CONSULTING**")
    st.write(f"User: **{st.session_state.user}**")
    if st.button("Logout", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()
    st.caption("Receive / Out Tracker")
    st.caption(datetime.now().strftime("%Y-%m-%d %H:%M"))
