import streamlit as st
import pandas as pd
import sqlite3
import os
import hashlib
from datetime import datetime

# =========================================================
# 1. CONFIG & BRANDING
# =========================================================
st.set_page_config(page_title="Mekgoro Inventory", layout="centered")

st.markdown("""
<style>
    .stButton > button { width: 100%; height: 3.5rem; border-radius: 12px; font-weight: bold; background-color: #1E3A8A; color: white; }
    .stSelectbox label, .stTextInput label { font-weight: bold; }
</style>
""", unsafe_allow_html=True)

if os.path.exists("logo.png"):
    st.image("logo.png", width=180)

# =========================================================
# 2. SECURITY
# =========================================================
def hash_pwd(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

MASTER_PASSWORD = hash_pwd("Mekgoro2024") 

if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.subheader("Partner Access Portal")
    user = st.selectbox("Select Staff Member", ["Ndule", "Tshepo", "Biino", "Anthony", "Mike"])
    pwd = st.text_input("Enter Master Password", type="password")
    if st.button("Enter Terminal"):
        if hash_pwd(pwd) == MASTER_PASSWORD:
            st.session_state.auth = True
            st.session_state.user = user
            st.rerun()
        else:
            st.error("Incorrect Password")
    st.stop()

# =========================================================
# 3. DATABASE
# =========================================================
db = sqlite3.connect("mekgoro_inventory.db", check_same_thread=False)

def init_db():
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty INTEGER)")
    db.execute("CREATE TABLE IF NOT EXISTS supplier_memory (supplier TEXT, item_name TEXT, UNIQUE(supplier, item_name))")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty INTEGER, ref TEXT, user TEXT, timestamp TEXT, supplier TEXT)")
    db.commit()

init_db()

# =========================================================
# 4. NAVIGATION
# =========================================================
st.caption(f"👤 Active User: {st.session_state.user}")
mode = st.radio("", ["📊 Stock", "📥 Receive", "📤 Dispatch", "🕒 History"], horizontal=True)

# ---------------------------------------------------------
# TAB 1: STOCK VIEW
# ---------------------------------------------------------
if mode == "📊 Stock":
    st.subheader("Warehouse Inventory Status")
    df = pd.read_sql("SELECT item_name as 'Item Description', qty as 'Stock Count' FROM assets ORDER BY item_name", db)
    if df.empty:
        st.info("Warehouse is empty.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# TAB 2: RECEIVE (ENFORCED EXISTING SUPPLIER)
# ---------------------------------------------------------
elif mode == "📥 Receive":
    st.subheader("New Stock Entry")
    
    # Get only existing/old suppliers from memory
    existing_suppliers = pd.read_sql("SELECT DISTINCT supplier FROM supplier_memory", db)['supplier'].tolist()
    
    # Force selection from existing list
    col_v1, col_v2 = st.columns([2, 1])
    
    if not existing_suppliers:
        st.warning("No suppliers in memory yet. Please add your first one below.")
        is_new = True
    else:
        is_new = col_v2.checkbox("New Supplier?")
        vendor = col_v1.selectbox("Select Existing Supplier", sorted(existing_suppliers), disabled=is_new)
    
    if is_new:
        vendor_name = st.text_input("Type NEW Supplier Name (e.g., Lock it)")
    else:
        vendor_name = vendor

    if vendor_name:
        # Load items specifically for THIS supplier
        history = pd.read_sql("SELECT item_name FROM supplier_memory WHERE supplier = ?", db, params=(vendor_name,))['item_name'].tolist()
        
        with st.form("in_form", clear_on_submit=True):
            st.write(f"Predictive Item List for **{vendor_name}**:")
            p_name = st.selectbox("Known Items", ["-- Select --"] + sorted(history))
            
            manual = st.text_input("OR Add New Item (if not in list above)")
            final_name = manual.strip() if manual else p_name
            
            c1, c2 = st.columns(2)
            qty = c1.number_input("Quantity", min_value=1, step=1)
            ref = c2.text_input("Invoice / Ref #")
            
            if st.form_submit_button("Confirm & Update Warehouse"):
                if final_name and final_name != "-- Select --":
                    db.execute("INSERT INTO assets (item_name, qty) VALUES (?, ?) ON CONFLICT(item_name) DO UPDATE SET qty = qty + excluded.qty", (final_name, int(qty)))
                    db.execute("INSERT OR IGNORE INTO supplier_memory VALUES (?, ?)", (vendor_name, final_name))
                    db.execute("INSERT INTO logs VALUES ('IN', ?, ?, ?, ?, ?, ?)", (final_name, int(qty), ref, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M"), vendor_name))
                    db.commit()
                    st.success(f"Stock Updated: {final_name}")
                    st.rerun()

# ---------------------------------------------------------
# TAB 3 & 4: DISPATCH & HISTORY (STAY THE SAME)
# ---------------------------------------------------------
elif mode == "📤 Dispatch":
    st.subheader("Dispatch to Site")
    stock = pd.read_sql("SELECT item_name, qty FROM assets WHERE qty > 0", db)
    if stock.empty:
        st.warning("No stock available.")
    else:
        with st.form("out_form"):
            choice = st.selectbox("Select Item", stock['item_name'].tolist())
            bal = stock[stock['item_name'] == choice]['qty'].values[0]
            st.info(f"In Warehouse: {int(bal)}")
            d_qty = st.number_input("Dispatch Quantity", 1, max_value=int(bal), step=1)
            site = st.text_input("Project / Site Name")
            if st.form_submit_button("Confirm Dispatch"):
                db.execute("UPDATE assets SET qty = qty - ? WHERE item_name = ?", (int(d_qty), choice))
                db.execute("INSERT INTO logs VALUES ('OUT', ?, ?, ?, ?, ?, 'INTERNAL')", (choice, int(d_qty), site, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
                db.commit()
                st.rerun()

elif mode == "🕒 History":
    st.subheader("Transaction History")
    logs = pd.read_sql("SELECT timestamp as 'Time', type as 'Action', item_name as 'Item', qty as 'Qty', ref as 'Reference', user as 'Staff' FROM logs ORDER BY timestamp DESC LIMIT 25", db)
    st.dataframe(logs, use_container_width=True, hide_index=True)
