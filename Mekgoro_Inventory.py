import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# ────────────────────────────────────────────────
# PAGE CONFIG – Mobile friendly
# ────────────────────────────────────────────────
st.set_page_config(
    page_title="Mekgoro Inventory",
    page_icon="logo.png",
    layout="wide",
    initial_sidebar_state="collapsed"  # collapsed on mobile
)

# Mobile optimizations: larger fonts, better spacing
st.markdown("""
    <style>
    @media (max-width: 768px) {
        .stApp { padding: 8px; }
        h1 { font-size: 1.8rem !important; }
        h2, h3 { font-size: 1.4rem !important; }
        .stButton > button { 
            width: 100%; 
            height: 50px; 
            font-size: 18px; 
            margin: 8px 0;
        }
        .stTextInput > div > div > input,
        .stNumberInput > div > div > input {
            font-size: 18px;
            padding: 12px;
        }
        .stock-big { font-size: 36px !important; }
        .metric-label { font-size: 16px !important; }
        .stTabs [data-baseweb="tab-list"] {
            flex-wrap: wrap !important;
            gap: 8px !important;
        }
        .stTabs [data-baseweb="tab"] {
            font-size: 16px !important;
            padding: 10px 16px !important;
        }
    }
    .success-msg { background-color: #e8f5e9; padding: 16px; border-radius: 8px; margin: 16px 0; font-size: 16px; }
    .warning-msg { background-color: #fff3cd; padding: 16px; border-radius: 8px; margin: 16px 0; font-size: 16px; }
    .error-msg  { background-color: #ffebee;  padding: 16px; border-radius: 8px; margin: 16px 0; font-size: 16px; }
    .stock-big  { font-size: 48px; font-weight: bold; color: #006400; text-align: center; margin: 24px 0; }
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
# LOGIN – with logo
# ────────────────────────────────────────────────
if "user" not in st.session_state:
    st.image("logo.png", width=300, use_column_width=True)
    st.markdown("<h3 style='text-align: center; color: #006400;'>MEKGORO CONSULTING</h3>", unsafe_allow_html=True)
    st.title("Inventory Login")
    
    users = sorted(["Anthony", "Biino", "Mike", "Ndule", "Tshepo"])
    user = st.selectbox("Select your name", users, key="login_user_select")
    
    if st.button("Login", type="primary", use_container_width=True):
        st.session_state.user = user
        st.rerun()
    st.stop()

# ────────────────────────────────────────────────
# MAIN PAGE – logo on top
# ────────────────────────────────────────────────
st.image("logo.png", width=300, use_column_width=True)
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
        st.info("No items in stock yet. Start receiving goods.")
    else:
        def color_qty(val):
            if val <= 0: return 'color: red; font-weight: bold;'
            if val <= 10: return 'color: #d97706; font-weight: bold;'
            return ''
        
        styled = df.style.format({"quantity": "{:,}"}).map(color_qty, subset=["quantity"])
        st.dataframe(styled, use_container_width=True, hide_index=True)

# ────────────────────────────────────────────────
# TAB: RECEIVE GOODS
# ────────────────────────────────────────────────
with tab_in:
    st.subheader("Receive Goods")
    
    supplier = st.text_input("Supplier", placeholder="e.g. Omnisurge", key="rec_supplier")
    ref = st.text_input("Invoice / Ref", placeholder="e.g. ION127436", key="rec_ref")
    
    item = st.text_input("Item", placeholder="e.g. Nitrile Gloves Large Blue", key="rec_item")
    
    qty = st.number_input("Quantity Received", min_value=0, step=1, key="rec_qty")
    
    if st.button("Confirm Receive", type="primary", use_container_width=True):
        item = item.strip()
        if not item:
            st.markdown('<div class="warning-msg">Enter item description</div>', unsafe_allow_html=True)
        elif qty <= 0:
            st.markdown('<div class="warning-msg">Quantity > 0 required</div>', unsafe_allow_html=True)
        else:
            update_stock(item, qty, "receive", ref, supplier)
            st.markdown(f"""
                <div class="success-msg">
                Received <b>{qty:,}</b> × <b>{item}</b> from <b>{supplier or 'Unknown'}</b><br>
                Ref: {ref or 'None'}
                </div>
            """, unsafe_allow_html=True)
            st.rerun()

# ────────────────────────────────────────────────
# TAB: GOODS OUT
# ────────────────────────────────────────────────
with tab_out:
    st.subheader("Goods Out")
    
    item = st.text_input("Item", placeholder="e.g. Nitrile Gloves Large Blue", key="out_item")
    
    current = get_current_stock(item) if item.strip() else 0
    st.markdown(f'<div class="stock-big">{current:,}</div>', unsafe_allow_html=True)
    st.markdown('<div class="metric-label">Current Stock</div>', unsafe_allow_html=True)
    
    qty_out = st.number_input("Quantity Leaving", min_value=0, step=1, key="out_qty")
    
    client = st.text_input("Client / Site", placeholder="e.g. Client XYZ", key="out_client")
    client_ref = st.text_input("PO / Order Ref", placeholder="e.g. PO-2026-045", key="out_ref")
    
    if st.button("Confirm Out", type="primary", use_container_width=True):
        item = item.strip()
        if not item:
            st.markdown('<div class="warning-msg">Enter item description</div>', unsafe_allow_html=True)
        elif qty_out <= 0:
            st.markdown('<div class="warning-msg">Quantity > 0 required</div>', unsafe_allow_html=True)
        elif current < qty_out:
            st.markdown(f"""
                <div class="error-msg">
                Not enough stock!<br>
                Only {current:,} available.
                </div>
            """, unsafe_allow_html=True)
        else:
            update_stock(item, -qty_out, "out", client_ref, client)
            st.markdown(f"""
                <div class="success-msg">
                Released <b>{qty_out:,}</b> × <b>{item}</b> to <b>{client or 'Unknown'}</b><br>
                Ref: {client_ref or 'None'}
                </div>
            """, unsafe_allow_html=True)
            st.rerun()

# ────────────────────────────────────────────────
# TAB: HISTORY
# ────────────────────────────────────────────────
with tab_history:
    st.subheader("History")
    
    logs = pd.read_sql("SELECT * FROM movements ORDER BY timestamp DESC LIMIT 100", db)
    
    if logs.empty:
        st.info("No movements yet.")
    else:
        logs['type'] = logs['type'].replace({'receive': 'IN', 'out': 'OUT'})
        logs['quantity'] = logs['quantity'].apply(lambda x: f"+{x:,}" if x > 0 else f"{x:,}")
        
        st.dataframe(logs[['timestamp', 'type', 'item_name', 'quantity', 'reference', 'party', 'user']], 
                     use_container_width=True, hide_index=True)

# ────────────────────────────────────────────────
# SIDEBAR
# ────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### MEKGORO CONSULTING")
    st.write(f"**User:** {st.session_state.user}")
    if st.button("Logout", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
    st.markdown("---")
    st.caption("Inventory – Receive & Out")
    st.caption(datetime.now().strftime("%Y-%m-%d %H:%M"))
