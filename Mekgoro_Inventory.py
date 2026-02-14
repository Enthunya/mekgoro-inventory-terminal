import streamlit as st
import pandas as pd
import sqlite3
import os
import hashlib
from datetime import datetime

# =========================================================
# 1. BRANDING & DEVICE OPTIMIZATION
# =========================================================
st.set_page_config(page_title="Mekgoro Inventory", layout="centered")

st.markdown("""
<style>
    .stButton > button { width: 100%; height: 3.5rem; border-radius: 12px; font-weight: bold; background-color: #1E3A8A; color: white; }
    .stMetric { background-color: #f0f2f6; padding: 10px; border-radius: 10px; border: 1px solid #dcdfe4; }
</style>
""", unsafe_allow_html=True)

if os.path.exists("logo.png"):
    st.image("logo.png", width=180)

# =========================================================
# 2. SECURITY (MASTER PASSWORD)
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
# 3. DATABASE (ASSETS NOW INCLUDE UNIT_COST)
# =========================================================
db = sqlite3.connect("mekgoro_inventory.db", check_same_thread=False)

def init_db():
    db.execute("""CREATE TABLE IF NOT EXISTS assets 
               (item_name TEXT PRIMARY KEY, qty INTEGER, unit_cost REAL DEFAULT 0)""")
    db.execute("CREATE TABLE IF NOT EXISTS supplier_memory (supplier TEXT, item_name TEXT, UNIQUE(supplier, item_name))")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty INTEGER, ref TEXT, user TEXT, timestamp TEXT, supplier TEXT, cost REAL)")
    db.commit()

init_db()

# =========================================================
# 4. NAVIGATION
# =========================================================
st.caption(f"👤 Active User: {st.session_state.user}")
mode = st.radio("", ["📊 Stock", "📥 Receive", "📤 Dispatch", "🕒 History"], horizontal=True)

# ---------------------------------------------------------
# TAB 1: STOCK VIEW (WITH FINANCIALS)
# ---------------------------------------------------------
if mode == "📊 Stock":
    st.subheader("Warehouse Inventory Status")
    
    # Calculate total warehouse value
    df = pd.read_sql("SELECT item_name, qty, unit_cost, (qty * unit_cost) as total_val FROM assets ORDER BY item_name", db)
    
    if df.empty:
        st.info("Warehouse is empty.")
    else:
        total_wh_value = df['total_val'].sum()
        st.metric("Total Warehouse Value", f"R {total_wh_value:,.2f}")
        
        # Display clean table for partners
        display_df = df.rename(columns={
            "item_name": "Item Description",
            "qty": "Stock",
            "unit_cost": "Unit Cost (R)",
            "total_val": "Total Value (R)"
        })
        st.dataframe(display_df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# TAB 2: RECEIVE (UPDATING QUANTITY AND PRICE)
# ---------------------------------------------------------
elif mode == "📥 Receive":
    st.subheader("New Stock Entry")
    
    existing_suppliers = pd.read_sql("SELECT DISTINCT supplier FROM supplier_memory", db)['supplier'].tolist()
    is_new_vendor = st.checkbox("➕ Add a New Supplier")
    
    if is_new_vendor or not existing_suppliers:
        vendor_name = st.text_input("Type New Supplier Name")
    else:
        vendor_name = st.selectbox("Select Existing Supplier", sorted(existing_suppliers))
    
    if vendor_name:
        history_items = pd.read_sql("SELECT item_name FROM supplier_memory WHERE supplier = ?", db, params=(vendor_name,))['item_name'].tolist()
        
        with st.form("in_form", clear_on_submit=True):
            st.markdown(f"### Receiving from: **{vendor_name}**")
            
            p_name = st.selectbox("Option A: Pick Regular Stock", ["-- Select --"] + sorted(history_items)) if history_items else "-- Select --"
            manual = st.text_input("Option B: Enter New Stock Item")
            final_name = manual.strip() if manual else p_name
            
            st.divider()
            c1, c2, c3 = st.columns(3)
            qty = c1.number_input("Qty Received", min_value=1, step=1)
            cost = c2.number_input("Unit Cost (R)", min_value=0.0, step=0.01)
            ref = c3.text_input("Invoice / Ref #")
            
            if st.form_submit_button("Confirm & Update Warehouse"):
                if not final_name or final_name == "-- Select --":
                    st.error("Please provide an item name.")
                else:
                    # UPDATING REPEAT STOCK: Adds Qty and Updates to the LATEST Cost
                    db.execute("""INSERT INTO assets (item_name, qty, unit_cost) VALUES (?, ?, ?) 
                               ON CONFLICT(item_name) DO UPDATE SET 
                               qty = qty + excluded.qty,
                               unit_cost = excluded.unit_cost""", (final_name, int(qty), cost))
                    
                    db.execute("INSERT OR IGNORE INTO supplier_memory VALUES (?, ?)", (vendor_name, final_name))
                    db.execute("INSERT INTO logs VALUES ('IN', ?, ?, ?, ?, ?, ?, ?)", 
                               (final_name, int(qty), ref, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M"), vendor_name, cost))
                    db.commit()
                    st.success(f"Stock Updated! Warehouse value increased by R {qty * cost:,.2f}")
                    st.rerun()

# ---------------------------------------------------------
# TABS 3 & 4: DISPATCH & HISTORY
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
                db.execute("INSERT INTO logs VALUES ('OUT', ?, ?, ?, ?, ?, 'INTERNAL', 0)", (choice, int(d_qty), site, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M"), "INTERNAL"))
                db.commit()
                st.rerun()

elif mode == "🕒 History":
    st.subheader("Transaction History")
    logs = pd.read_sql("SELECT timestamp as 'Time', type as 'Action', item_name as 'Item', qty as 'Qty', ref as 'Reference', user as 'Staff' FROM logs ORDER BY timestamp DESC LIMIT 25", db)
    st.dataframe(logs, use_container_width=True, hide_index=True)
