import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime

# --- 1. BRANDING & SECURITY ---
st.set_page_config(page_title="Mekgoro Inventory", layout="wide")

# Change this to your secret code before sharing!
MASTER_PASSWORD = "Mekgoro2024" 

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

def login_screen():
    col1, col2 = st.columns([1, 2])
    if os.path.exists("logo.png"):
        col1.image("logo.png", width=180)
    else:
        col1.title("🏗️ MEKGORO")
    
    col2.title("Secure Access")
    pwd = col2.text_input("Enter Master Password", type="password")
    # Updated: Removed 'Driver' from Tshepo's name
    user = col2.selectbox("Select Your Name", ["Ndule", "Tshepo", "Biino", "Anthony", "Mike"])
    
    if col2.button("Enter Terminal"):
        if pwd == MASTER_PASSWORD:
            st.session_state.authenticated = True
            st.session_state.user = user
            st.rerun()
        else:
            st.error("Incorrect Password")

if not st.session_state.authenticated:
    login_screen()
    st.stop()

# --- 2. DATABASE LOGIC ---
db = sqlite3.connect("mekgoro_cloud.db", check_same_thread=False)

def init_db():
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty INTEGER)")
    db.execute("CREATE TABLE IF NOT EXISTS supplier_memory (supplier TEXT, item_name TEXT, UNIQUE(supplier, item_name))")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty INTEGER, ref_no TEXT, file_path TEXT, user TEXT, timestamp TEXT, supplier TEXT)")
    db.commit()

init_db()

# --- 3. MAIN APP INTERFACE ---
col_logo, col_title = st.columns([1, 5])
if os.path.exists("logo.png"): col_logo.image("logo.png", width=100)
col_title.title("Mekgoro Inventory Terminal")
st.write(f"Logged in: **{st.session_state.user}** | {datetime.now().strftime('%d %b %Y')}")

tab1, tab2, tab3 = st.tabs(["📊 Warehouse Ledger", "📥 Stock IN (Purchases)", "📤 Stock OUT (Deliveries)"])

with tab1:
    st.subheader("Current Warehouse Stock")
    df_all = pd.read_sql("SELECT item_name as 'Item', qty as 'Stock' FROM assets ORDER BY item_name ASC", db)
    st.dataframe(df_all, use_container_width=True, height=400)
    
    st.divider()
    st.subheader("🕒 Recent Activity")
    logs = pd.read_sql("SELECT timestamp, type, item_name, qty, ref_no, user FROM logs ORDER BY timestamp DESC LIMIT 10", db)
    st.table(logs)

with tab2:
    st.subheader("📥 Receive Stock (Self-Learning)")
    suppliers = pd.read_sql("SELECT DISTINCT supplier FROM supplier_memory", db)['supplier'].tolist()
    
    s_col1, s_col2 = st.columns(2)
    vendor_choice = s_col1.selectbox("Supplier", ["-- New Supplier --"] + sorted(suppliers))
    vendor = s_col2.text_input("New Supplier Name") if vendor_choice == "-- New Supplier --" else vendor_choice

    if vendor:
        # Pulls items previously bought from this specific vendor
        items = pd.read_sql("SELECT item_name FROM supplier_memory WHERE supplier = ?", db, params=(vendor,))['item_name'].tolist()
        
        with st.form("in_form", clear_on_submit=True):
            p_name = st.selectbox("Search Known Items", ["-- Select --"] + sorted(items))
            manual = st.text_input("OR Type New Item Name (Exactly as per Invoice)")
            final_name = manual.strip() if manual else p_name
            
            qty = st.number_input("Quantity", min_value=1, step=1)
            ref = st.text_input("Invoice / Ref #")
            
            if st.form_submit_button("Update Warehouse"):
                if final_name and final_name != "-- Select --":
                    # Updates Warehouse Stock immediately
                    db.execute("INSERT INTO assets (item_name, qty) VALUES (?, ?) ON CONFLICT(item_name) DO UPDATE SET qty = qty + excluded.qty", (final_name, int(qty)))
                    # Remembers item for this supplier
                    db.execute("INSERT OR IGNORE INTO supplier_memory VALUES (?, ?)", (vendor, final_name))
                    # Logs the transaction
                    db.execute("INSERT INTO logs VALUES ('PURCHASE', ?, ?, ?, ?, ?, ?, ?)", (final_name, int(qty), ref, "", st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M"), vendor))
                    db.commit()
                    st.success(f"Stock Updated! Added {qty} units of {final_name}")
                    st.rerun()

with tab3:
    st.subheader("📤 Site Delivery")
    stock = pd.read_sql("SELECT item_name, qty FROM assets WHERE qty > 0", db)
    if stock.empty:
        st.warning("Warehouse is empty. Record a Purchase first.")
    else:
        with st.form("out_form"):
            choice = st.selectbox("Select Item", stock['item_name'].tolist())
            bal = stock[stock['item_name'] == choice]['qty'].values[0]
            st.info(f"Available: {int(bal)}")
            out_qty = st.number_input("Dispatch Qty", min_value=1, step=1)
            site = st.text_input("Project Site / Client")
            
            if st.form_submit_button("Confirm Dispatch"):
                if out_qty <= bal:
                    db.execute("UPDATE assets SET qty = qty - ? WHERE item_name = ?", (int(out_qty), choice))
                    db.execute("INSERT INTO logs VALUES ('DELIVERY', ?, ?, ?, ?, ?, ?, 'INTERNAL')", (choice, int(out_qty), site, "", st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M"), "INTERNAL"))
                    db.commit()
                    st.success(f"Dispatched {out_qty} to {site}")
                    st.rerun()
                else:
                    st.error("Insufficient stock!")
