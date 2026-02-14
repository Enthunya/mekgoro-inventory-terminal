import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime

# --- 1. CONFIG & DATABASE ---
st.set_page_config(page_title="Mekgoro Inventory", layout="wide")
db = sqlite3.connect("mekgoro_learning.db", check_same_thread=False)

if not os.path.exists("uploads"):
    os.makedirs("uploads")

def init_db():
    # Assets: Current Stock
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty INTEGER)")
    # Logs: History of all movements
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty INTEGER, ref_no TEXT, file_path TEXT, user TEXT, timestamp TEXT, supplier TEXT)")
    # Memory: Links Suppliers to specific Items to power the search
    db.execute("CREATE TABLE IF NOT EXISTS supplier_memory (supplier TEXT, item_name TEXT, UNIQUE(supplier, item_name))")
    db.commit()

init_db()

# --- 2. LOGIN ---
if "user" not in st.session_state:
    st.title("🛡️ Mekgoro Secure Login")
    name = st.selectbox("Staff Member", ["Ndule", "Tshepo (Driver)", "Biino", "Anthony", "Mike"])
    if st.button("Access Terminal"):
        st.session_state.user = name
        st.rerun()
    st.stop()

# --- 3. INTERFACE ---
st.title(f"🏗️ Mekgoro Terminal | User: {st.session_state.user}")
tab1, tab2, tab3 = st.tabs(["📊 Warehouse Ledger", "📥 Purchases (Self-Learning)", "📤 Site Deliveries"])

with tab1:
    st.subheader("Current Warehouse Stock")
    search_main = st.text_input("🔍 Search Inventory...")
    df_all = pd.read_sql("SELECT item_name as 'Item Description', qty as 'Stock' FROM assets ORDER BY item_name ASC", db)
    if search_main:
        df_all = df_all[df_all['Item Description'].str.contains(search_main, case=False, na=False)]
    st.dataframe(df_all, use_container_width=True)

with tab2:
    st.subheader("📥 Record Purchase")
    
    # 1. Get List of existing suppliers from memory
    existing_suppliers = pd.read_sql("SELECT DISTINCT supplier FROM supplier_memory", db)['supplier'].tolist()
    
    col_s1, col_s2 = st.columns([1, 1])
    vendor_choice = col_s1.selectbox("Select Existing Supplier", ["-- New Supplier --"] + sorted(existing_suppliers))
    
    if vendor_choice == "-- New Supplier --":
        vendor = col_s2.text_input("Type New Supplier Name (e.g., Lock it)")
    else:
        vendor = vendor_choice

    if vendor:
        st.markdown(f"### Entry for: **{vendor}**")
        
        # 2. Get items specifically for THIS supplier
        supplier_items = pd.read_sql("SELECT item_name FROM supplier_memory WHERE supplier = ?", db, params=(vendor,))['item_name'].tolist()
        
        with st.form("purchase_form", clear_on_submit=True):
            st.write("Type to filter items we've bought from them before:")
            
            # This search box acts as the predictive filter
            p_name = st.selectbox("Predictive Item Search", ["-- Type/Select Item --"] + sorted(supplier_items))
            
            new_item_toggle = st.checkbox("Adding a NEW item from this supplier?")
            manual_name = st.text_input("Enter Item Description (Exactly as per Invoice)") if new_item_toggle or not supplier_items else ""
            
            final_name = manual_name.strip() if manual_name else p_name
            
            col1, col2 = st.columns(2)
            p_qty = col1.number_input("Quantity Received", min_value=1, step=1)
            p_ref = col2.text_input("Invoice / Document #")
            
            uploaded_file = st.file_uploader("Upload Invoice Photo/PDF", type=['pdf', 'png', 'jpg', 'jpeg'])
            
            if st.form_submit_button("Confirm & Save"):
                if not final_name or final_name == "-- Type/Select Item --":
                    st.error("Please provide an Item Name.")
                else:
                    f_path = ""
                    if uploaded_file:
                        f_path = os.path.join("uploads", f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uploaded_file.name}")
                        with open(f_path, "wb") as f:
                            f.write(uploaded_file.getbuffer())
                    
                    # UPDATE ALL TABLES
                    # A. Asset Stock
                    db.execute("INSERT INTO assets (item_name, qty) VALUES (?, ?) ON CONFLICT(item_name) DO UPDATE SET qty = qty + excluded.qty", (final_name, int(p_qty)))
                    # B. Movement Log
                    db.execute("INSERT INTO logs VALUES ('PURCHASE', ?, ?, ?, ?, ?, ?, ?)", (final_name, int(p_qty), p_ref, f_path, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M"), vendor))
                    # C. The Brain (Memory) - Link this item to this supplier
                    db.execute("INSERT OR IGNORE INTO supplier_memory VALUES (?, ?)", (vendor, final_name))
                    
                    db.commit()
                    st.success(f"Saved! The system now remembers {final_name} belongs to {vendor}.")
                    st.rerun()

with tab3:
    st.subheader("📤 Record Site Delivery")
    items_list = pd.read_sql("SELECT item_name, qty FROM assets WHERE qty > 0", db)
    if not items_list.empty:
        with st.form("delivery_form"):
            d_choice = st.selectbox("Select Item", items_list['item_name'].tolist())
            d_bal = items_list[items_list['item_name'] == d_choice]['qty'].values[0]
            st.info(f"Available: {int(d_bal)}")
            d_qty = st.number_input("Quantity Out", min_value=1, step=1)
            d_site = st.text_input("Project / Site Name")
            if st.form_submit_button("Confirm Dispatch"):
                if d_qty > d_bal: st.error("Shortage!")
                else:
                    db.execute("UPDATE assets SET qty = qty - ? WHERE item_name = ?", (int(d_qty), d_choice))
                    db.execute("INSERT INTO logs VALUES ('DELIVERY', ?, ?, ?, ?, ?, ?, 'INTERNAL')", (d_choice, int(d_qty), d_site, "", st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
                    db.commit()
                    st.rerun()
