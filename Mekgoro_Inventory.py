import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime

# --- 1. CONFIG & DATABASE ---
st.set_page_config(page_title="Mekgoro Inventory", layout="wide")
db = sqlite3.connect("mekgoro_final.db", check_same_thread=False)

if not os.path.exists("uploads"):
    os.makedirs("uploads")

def init_db():
    # item_name is the key; qty is always a whole number (INTEGER)
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
tab1, tab2, tab3 = st.tabs(["📊 Warehouse Ledger", "📥 Purchases (Stock IN)", "📤 Deliveries (Stock OUT)"])

with tab1:
    st.subheader("Current Warehouse Stock")
    search_main = st.text_input("🔍 Search Items...", placeholder="Search for anything in the warehouse")
    # Fetch data and ensure qty is treated as a whole number
    df_all = pd.read_sql("SELECT item_name as 'Item Description', qty as 'Stock' FROM assets ORDER BY item_name ASC", db)
    if search_main:
        df_all = df_all[df_all['Item Description'].str.contains(search_main, case=False, na=False)]
    st.dataframe(df_all, use_container_width=True, height=400)

    st.divider()
    st.subheader("🕒 Activity History")
    # Show the last 15 movements
    logs = pd.read_sql("SELECT timestamp as 'Time', type as 'Action', item_name as 'Item', qty as 'Qty', ref_no as 'Ref/Project', user as 'Staff' FROM logs ORDER BY timestamp DESC LIMIT 15", db)
    st.table(logs)

with tab2:
    st.subheader("📥 Record New Purchase")
    st.info("Manual Entry: Type the item details exactly as they appear on the invoice.")
    
    with st.form("purchase_form", clear_on_submit=True):
        p_name = st.text_input("Item Description (e.g., Nitrile Blue Gloves Large)")
        p_qty = st.number_input("Quantity Received (Whole Numbers)", min_value=1, step=1, value=1)
        p_ref = st.text_input("Supplier / Invoice # (e.g., Omnisurge ION127436)")
        
        # Uploading the invoice/photo as proof
        uploaded_file = st.file_uploader("Upload Invoice Photo or PDF", type=['pdf', 'png', 'jpg', 'jpeg'])
        
        if st.form_submit_button("Confirm & Add to Stock"):
            if not p_name:
                st.error("Item Description cannot be empty.")
            else:
                f_path = ""
                if uploaded_file:
                    f_path = os.path.join("uploads", f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uploaded_file.name}")
                    with open(f_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                
                # Update ledger: If item exists, add qty. If not, create it.
                db.execute("INSERT INTO assets (item_name, qty) VALUES (?, ?) ON CONFLICT(item_name) DO UPDATE SET qty = qty + excluded.qty",
                           (p_name.strip(), int(p_qty)))
                
                # Record the log
                db.execute("INSERT INTO logs VALUES ('PURCHASE', ?, ?, ?, ?, ?, ?)", 
                           (p_name.strip(), int(p_qty), p_ref, f_path, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
                db.commit()
                st.success(f"Successfully added {int(p_qty)} units of {p_name}")
                st.rerun()

with tab3:
    st.subheader("📤 Record Site Delivery")
    # Load items that actually have stock
    items_list = pd.read_sql("SELECT item_name, qty FROM assets WHERE qty > 0", db)
    
    if items_list.empty:
        st.warning("Warehouse is currently empty. No stock to deliver.")
    else:
        with st.form("delivery_form"):
            d_choice = st.selectbox("Select Item to Deliver", items_list['item_name'].tolist())
            d_bal = items_list[items_list['item_name'] == d_choice]['qty'].values[0]
            st.info(f"Available: {int(d_bal)}")
            
            d_qty = st.number_input("Quantity to Dispatch", min_value=1, step=1, value=1)
            d_site = st.text_input("Project Name / Site")
            
            if st.form_submit_button("Confirm Dispatch"):
                if d_qty > d_bal:
                    st.error(f"Cannot dispatch {int(d_qty)}. Only {int(d_bal)} in stock.")
                else:
                    db.execute("UPDATE assets SET qty = qty - ? WHERE item_name = ?", (int(d_qty), d_choice))
                    db.execute("INSERT INTO logs VALUES ('DELIVERY', ?, ?, ?, ?, ?, ?)", 
                               (d_choice, int(d_qty), d_site, "", st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
                    db.commit()
                    st.warning(f"Dispatched {int(d_qty)} units to {d_site}")
                    st.rerun()
