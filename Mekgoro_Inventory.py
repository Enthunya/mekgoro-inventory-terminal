import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# ────────────────────────────────────────────────
# PAGE CONFIG
# ────────────────────────────────────────────────
st.set_page_config(page_title="Mekgoro Inventory", page_icon="logo.png", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #f8f9fa; }
    h1, h2, h3 { color: #006400; }
    .success-msg { background-color: #e8f5e9; padding: 14px; border-radius: 8px; margin: 12px 0; font-size: 16px; }
    .warning-msg { background-color: #fff3cd; padding: 14px; border-radius: 8px; margin: 12px 0; font-size: 16px; }
    .error-msg  { background-color: #ffebee;  padding: 14px; border-radius: 8px; margin: 12px 0; font-size: 16px; }
    .stock-big  { font-size: 42px; font-weight: bold; color: #006400; text-align: center; margin: 20px 0; }
    .metric-label { font-size: 18px; color: #555; text-align: center; }
    </style>
""", unsafe_allow_html=True)

# ────────────────────────────────────────────────
# DATABASE
# ────────────────────────────────────────────────
db = sqlite3.connect("mekgoro_inventory.db", check_same_thread=False)

def init_db():
    db.execute("""
        CREATE TABLE IF NOT EXISTS stock (
            item_name TEXT PRIMARY KEY,
            quantity INTEGER DEFAULT 0,
            last_update TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,               -- 'receive' or 'out'
            item_name TEXT,
            quantity INTEGER,
            reference TEXT,
            party TEXT,              -- supplier or client
            user TEXT,
            timestamp TEXT
        )
    """)
    db.commit()

init_db()

# ────────────────────────────────────────────────
# HELPERS
# ────────────────────────────────────────────────
def get_current_stock(item_name):
    row = pd.read_sql("SELECT quantity FROM stock WHERE item_name = ?", db, params=(item_name.strip(),))
    return row.iloc[0]['quantity'] if not row.empty else 0

def update_stock(item_name, qty_change, movement_type, reference="", party=""):
    item_name = item_name.strip()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user = st.session_state.user
    
    db.execute("""
        INSERT OR REPLACE INTO stock (item_name, quantity, last_update)
        VALUES (?, COALESCE((SELECT quantity FROM stock WHERE item_name=?), 0) + ?, ?)
    """, (item_name, item_name, qty_change, now))
    
    db.execute("""
        INSERT INTO movements (type, item_name, quantity, reference, party, user, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (movement_type, item_name, qty_change, reference, party, user, now))
    
    db.commit()

def get_known_items():
    df = pd.read_sql("SELECT DISTINCT item_name FROM stock ORDER BY item_name", db)
    return df['item_name'].tolist() if not df.empty else []

# ────────────────────────────────────────────────
# LOGIN
# ────────────────────────────────────────────────
if "user" not in st.session_state:
    st.title("Mekgoro Inventory – Login")
    user = st.selectbox("Select your name", ["Ndule", "Biino", "Anthony", "Mike"])
    if st.button("Login", type="primary"):
        st.session_state.user = user
        st.rerun()
    st.stop()

# ────────────────────────────────────────────────
# MAIN PAGE
# ────────────────────────────────────────────────
st.image("logo.png", width=380)
st.markdown("<h3 style='text-align: center; color: #006400;'>MEKGORO CONSULTING</h3>", unsafe_allow_html=True)
st.title(f"Inventory – {st.session_state.user}")

tab_stock, tab_in, tab_out, tab_history = st.tabs([
    "📊 Stock",
    "📥 Receive",
    "📤 Out",
    "📋 History"
])

# ────────────────────────────────────────────────
# TAB: STOCK OVERVIEW
# ────────────────────────────────────────────────
with tab_stock:
    st.subheader("Current Stock")
    
    df = pd.read_sql("SELECT item_name, quantity, last_update FROM stock ORDER BY item_name", db)
    
    if df.empty:
        st.info("No items in stock yet. Start by receiving goods.")
    else:
        def color_code(val):
            if val <= 0: return 'color: red; font-weight: bold;'
            if val <= 10: return 'color: #d97706; font-weight: bold;'
            return ''
        
        styled = df.style.format({"quantity": "{:,}"}).map(color_code, subset=["quantity"])
        st.dataframe(styled, use_container_width=True, hide_index=True)

# ────────────────────────────────────────────────
# TAB: RECEIVE
# ────────────────────────────────────────────────
with tab_in:
    st.subheader("Receive Goods (In)")
    
    supplier = st.text_input("Supplier", placeholder="e.g. Omnisurge (PTY) LTD")
    ref = st.text_input("Invoice / SO / Delivery Ref", placeholder="e.g. ION127436")
    
    known_items = get_known_items()
    item = st.text_input("Item", placeholder="e.g. Nitrile Examination Gloves - Large Blue")
    
    qty = st.number_input("Quantity Received", min_value=0, step=1)
    
    if st.button("Confirm Receive", type="primary"):
        item = item.strip()
        if not item:
            st.markdown('<div class="warning-msg">Please enter item description</div>', unsafe_allow_html=True)
        elif qty <= 0:
            st.markdown('<div class="warning-msg">Quantity must be greater than 0</div>', unsafe_allow_html=True)
        else:
            update_stock(item, qty, "receive", ref, supplier)
            st.markdown(f"""
                <div class="success-msg">
                <b>Received successfully!</b><br>
                {qty:,} × <b>{item}</b> from {supplier or 'Unknown'}<br>
                Ref: {ref or 'None'}
                </div>
            """, unsafe_allow_html=True)
            st.rerun()

# ────────────────────────────────────────────────
# TAB: GOODS OUT
# ────────────────────────────────────────────────
with tab_out:
    st.subheader("Goods Out (Delivery / Sale)")
    
    known_items = get_known_items()
    item = st.text_input("Item", placeholder="e.g. Nitrile Examination Gloves - Large Blue")
    
    current = get_current_stock(item) if item.strip() else 0
    st.markdown(f'<div class="metric-box">{current:,}</div>', unsafe_allow_html=True)
    st.markdown('<div class="metric-label">Current Stock</div>', unsafe_allow_html=True)
    
    qty_out = st.number_input("Quantity Leaving", min_value=0, step=1)
    
    client = st.text_input("Client / Site", placeholder="e.g. Client XYZ - Johannesburg")
    client_ref = st.text_input("Client PO / Order Ref", placeholder="e.g. PO-2026-045")
    
    if st.button("Confirm Out", type="primary"):
        item = item.strip()
        if not item:
            st.markdown('<div class="warning-msg">Please enter item description</div>', unsafe_allow_html=True)
        elif qty_out <= 0:
            st.markdown('<div class="warning-msg">Quantity must be greater than 0</div>', unsafe_allow_html=True)
        elif current < qty_out:
            st.markdown(f"""
                <div class="danger-msg">
                <b>Not enough stock!</b><br>
                Only {current:,} available – cannot release {qty_out:,}
                </div>
            """, unsafe_allow_html=True)
        else:
            update_stock(item, -qty_out, "out", client_ref, client)
            st.markdown(f"""
                <div class="success-msg">
                <b>Goods out recorded!</b><br>
                {qty_out:,} × <b>{item}</b> to {client or 'Unknown'}<br>
                Ref: {client_ref or 'None'}
                </div>
            """, unsafe_allow_html=True)
            st.rerun()

# ────────────────────────────────────────────────
# TAB: HISTORY
# ────────────────────────────────────────────────
with tab_history:
    st.subheader("Movement History")
    
    logs = pd.read_sql("""
        SELECT timestamp, type, item_name, quantity, reference, party, user
        FROM movements 
        ORDER BY timestamp DESC 
        LIMIT 100
    """, db)
    
    if logs.empty:
        st.info("No movements yet.")
    else:
        logs['type'] = logs['type'].replace({'receive': 'IN', 'out': 'OUT'})
        logs['quantity'] = logs['quantity'].apply(lambda x: f"+{x:,}" if x > 0 else f"{x:,}")
        
        st.dataframe(logs, use_container_width=True, hide_index=True)

# ────────────────────────────────────────────────
# SIDEBAR
# ────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### MEKGORO CONSULTING")
    st.write(f"**User:** {st.session_state.user}")
    if st.button("Logout"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
    st.markdown("---")
    st.caption("Simple In / Out Tracking")
    st.caption(datetime.now().strftime("%Y-%m-%d %H:%M"))
