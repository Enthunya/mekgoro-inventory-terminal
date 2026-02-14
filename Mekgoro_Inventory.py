import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime

# --- 1. CONFIG & SUPPLIER MEMORY ---
st.set_page_config(page_title="Mekgoro Inventory", layout="wide")
db = sqlite3.connect("mekgoro_predict.db", check_same_thread=False)

if not os.path.exists("uploads"):
    os.makedirs("uploads")

# ADD NEW SUPPLIERS AND THEIR ITEMS HERE
# This acts as the 'Auto-Complete' brain for the system
SUPPLIER_CATALOG = {
    "Omnisurge": [
        "Golden Hands Nitrile Blue Examination Large",
        "Nitrile Powder Free Gloves Medium",
        "Nitrile Powder Free Gloves Small",
        "Surgical Face Masks 3-Ply"
    ],
    "Lock it": [
        "Nylon Cable Ties 100mm",
        "Nylon Cable Ties 200mm",
        "Nitrile Coated Work Gloves",
        "Nut and Bolt Set M8",
        "Night Latch Lockset"
    ],
    "Manual Entry": []
}

def init_db():
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty INTEGER)")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty INTEGER, ref_no TEXT, file_path TEXT, user TEXT, timestamp TEXT)")
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
tab1, tab2, tab3 = st.tabs(["📊 Warehouse Ledger", "📥 Purchases", "📤 Deliveries"])

with tab1:
    st.subheader("Current Warehouse Stock")
    search_main = st.text_input("🔍 Quick Search Stock...")
    df_all = pd.read_sql("SELECT item_name as 'Item Description', qty as 'Stock' FROM assets ORDER BY item_name ASC", db)
    if search_main:
        df_all = df_all[df_all['Item Description'].str.contains(search_main, case=False, na=False)]
    st.dataframe(df_all, use_container_width=True)

with tab2:
    st.subheader("📥 Receive New Stock")
    
    # 1. Select Supplier First
    vendor = st.selectbox("Select Supplier", list(SUPPLIER_CATALOG.keys()))
    
    with st.form("purchase_form", clear_on_submit=True):
        # 2. Predictive Search based on Supplier
        st.write(f"**Items for {vendor}:**")
        
        # We combine the Catalog items with anything already in the DB for this vendor
        db_items = pd.read_sql("SELECT item_name FROM assets", db)['item_name'].tolist()
        available_suggestions = list(set(SUPPLIER_CATALOG[vendor] + db_items)) if vendor != "Manual Entry" else db_items
        
        # Tshepo types here, and the dropdown filters
        p_name = st.selectbox("Search/Select Item Name", [""] + sorted(available_suggestions), help="Type the first letter (e.g., 'N') to see matches.")
        
        # Backup if it's a brand new item not in our catalog yet
        manual_name = st.text_input("OR type new item name (if not in list)")
        
        final_name = manual_name.strip() if manual_name else p_name
        
        col1, col2 = st.columns(2)
        p_qty = col1.number_input("Quantity Received", min_value=1, step=1)
        p_ref = col2.text_input("Invoice / Ref #")
        
        uploaded_file = st.file_uploader("Upload Invoice Photo/PDF", type=['pdf', 'png', 'jpg', 'jpeg'])
        
        if st.form_submit_button("Confirm & Update Ledger"):
            if not final_name:
                st.error("Please enter or select an item.")
            else:
                f_path = ""
                if uploaded_file:
                    f_path = os.path.join("uploads", f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uploaded_file.name}")
                    with open(f_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                
                db.execute("INSERT INTO assets (item_name, qty) VALUES (?, ?) ON CONFLICT(item_name) DO UPDATE SET qty = qty + excluded.qty",
                           (final_name, int(p_qty)))
                db.execute("INSERT INTO logs VALUES ('PURCHASE', ?, ?, ?, ?, ?, ?)", 
                           (final_name, int(p_qty), p_ref, f_path, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
                db.commit()
                st.success(f"Added {int(p_qty)} x {final_name}")
                st.rerun()

with tab3:
    st.subheader("📤 Record Site Delivery")
    items_list = pd.read_sql("SELECT item_name, qty FROM assets WHERE qty > 0", db)
    
    if items_list.empty:
        st.warning("Warehouse is empty.")
    else:
        with st.form("delivery_form"):
            d_choice = st.selectbox("Select Item", items_list['item_name'].tolist())
            d_bal = items_list[items_list['item_name'] == d_choice]['qty'].values[0]
            st.write(f"📦 **Stock Available: {int(d_bal)}**")
            
            d_qty = st.number_input("Quantity Out", min_value=1, step=1)
            d_site = st.text_input("Project / Site Name")
            
            if st.form_submit_button("Confirm Dispatch"):
                if d_qty > d_bal:
                    st.error("Not enough stock!")
                else:
                    db.execute("UPDATE assets SET qty = qty - ? WHERE item_name = ?", (int(d_qty), d_choice))
                    db.execute("INSERT INTO logs VALUES ('DELIVERY', ?, ?, ?, ?, ?, ?)", 
                               (d_choice, int(d_qty), d_site, "", st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
                    db.commit()
                    st.rerun()
