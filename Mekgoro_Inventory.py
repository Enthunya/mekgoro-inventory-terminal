import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime

# --- 1. CONFIG & MEMORY ---
st.set_page_config(page_title="Mekgoro Inventory", layout="wide")
db = sqlite3.connect("mekgoro_intel.db", check_same_thread=False)

if not os.path.exists("uploads"):
    os.makedirs("uploads")

# "The Memory": Add other suppliers to this dictionary later
SUPPLIER_PROFILES = {
    "Omnisurge": {
        "common_items": ["Golden Hands Nitrile Blue Examination Large", "Nitrile Powder Free Gloves"],
        "ref_prefix": "ION",
        "tip": "Check the top right for 'Document No' starting with ION."
    }
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
tab1, tab2, tab3 = st.tabs(["📊 Warehouse Ledger", "📥 Intelligent Purchase", "📤 Deliveries"])

with tab1:
    st.subheader("Current Warehouse Stock")
    search_main = st.text_input("🔍 Search Items...")
    df_all = pd.read_sql("SELECT item_name as 'Item Description', qty as 'Stock' FROM assets ORDER BY item_name ASC", db)
    if search_main:
        df_all = df_all[df_all['Item Description'].str.contains(search_main, case=False, na=False)]
    st.dataframe(df_all, use_container_width=True)

with tab2:
    st.subheader("📥 Intelligent Purchase Entry")
    
    # Supplier Intelligence
    supplier = st.selectbox("Which supplier are you receiving from?", ["Manual Entry"] + list(SUPPLIER_PROFILES.keys()))
    
    if supplier != "Manual Entry":
        st.info(f"💡 **Assistant Tip for {supplier}:** {SUPPLIER_PROFILES[supplier]['tip']}")
    
    with st.form("purchase_form", clear_on_submit=True):
        # The Assistant: Provides known names to prevent spelling mistakes
        known_items = pd.read_sql("SELECT item_name FROM assets", db)['item_name'].tolist()
        if supplier in SUPPLIER_PROFILES:
            known_items = list(set(known_items + SUPPLIER_PROFILES[supplier]['common_items']))
        
        p_name = st.selectbox("Item Description (Select or Start Typing)", [""] + sorted(known_items))
        manual_name = st.text_input("OR type new item name here (if not in list above)")
        
        final_name = manual_name.strip() if manual_name else p_name
        
        col1, col2 = st.columns(2)
        p_qty = col1.number_input("Quantity Received (Whole #)", min_value=1, step=1)
        p_ref = col2.text_input("Invoice / Document #")
        
        uploaded_file = st.file_uploader("Upload Invoice Photo/PDF", type=['pdf', 'png', 'jpg', 'jpeg'])
        
        if st.form_submit_button("Confirm & Update Ledger"):
            if not final_name:
                st.error("Please provide an Item Description.")
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
                st.success(f"Successfully recorded {int(p_qty)} units of {final_name}")
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
            st.write(f"📦 **Warehouse Balance: {int(d_bal)}**")
            
            d_qty = st.number_input("Quantity Out", min_value=1, step=1)
            d_site = st.text_input("Project / Site Name")
            
            if st.form_submit_button("Confirm Dispatch"):
                if d_qty > d_bal:
                    st.error("Insufficient Stock!")
                else:
                    db.execute("UPDATE assets SET qty = qty - ? WHERE item_name = ?", (int(d_qty), d_choice))
                    db.execute("INSERT INTO logs VALUES ('DELIVERY', ?, ?, ?, ?, ?, ?)", 
                               (d_choice, int(d_qty), d_site, "", st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
                    db.commit()
                    st.rerun()
