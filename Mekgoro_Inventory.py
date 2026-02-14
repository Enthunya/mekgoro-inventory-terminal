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
    # Assets: This is your Warehouse Stock table
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty INTEGER)")
    # Memory: This links Suppliers to specific Items for predictive typing
    db.execute("CREATE TABLE IF NOT EXISTS supplier_memory (supplier TEXT, item_name TEXT, UNIQUE(supplier, item_name))")
    # Logs: The full history
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty INTEGER, ref_no TEXT, file_path TEXT, user TEXT, timestamp TEXT, supplier TEXT)")
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
    st.subheader("Current Warehouse Stock (Updates Automatically)")
    search_main = st.text_input("🔍 Search Inventory Items...", placeholder="e.g. Nitrile, Cable, Lock")
    
    # This view queries the 'assets' table which is updated by Purchases
    df_all = pd.read_sql("SELECT item_name as 'Item Description', qty as 'Total Available' FROM assets ORDER BY item_name ASC", db)
    if search_main:
        df_all = df_all[df_all['Item Description'].str.contains(search_main, case=False, na=False)]
    
    # Highlight the stock level so it's easy to read
    st.dataframe(df_all, use_container_width=True, height=400)

with tab2:
    st.subheader("📥 Receive New Stock")
    st.markdown("Select a supplier to see items we've bought from them before.")
    
    existing_suppliers = pd.read_sql("SELECT DISTINCT supplier FROM supplier_memory", db)['supplier'].tolist()
    
    col_s1, col_s2 = st.columns([1, 1])
    vendor_choice = col_s1.selectbox("Supplier Name", ["-- New Supplier --"] + sorted(existing_suppliers))
    
    if vendor_choice == "-- New Supplier --":
        vendor = col_s2.text_input("Type New Supplier Name")
    else:
        vendor = vendor_choice

    if vendor:
        # Get items linked to this supplier for predictive search
        supplier_items = pd.read_sql("SELECT item_name FROM supplier_memory WHERE supplier = ?", db, params=(vendor,))['item_name'].tolist()
        
        with st.form("purchase_form", clear_on_submit=True):
            # Predictive filtering: typing 'N' shows items starting with 'N' from this supplier
            p_name = st.selectbox("Predictive Item Search (History-based)", ["-- Type/Select Item --"] + sorted(supplier_items))
            
            new_item_toggle = st.checkbox("Adding a NEW item for this supplier?")
            manual_name = st.text_input("New Item Description (Exactly as per Invoice)") if new_item_toggle or not supplier_items else ""
            
            final_name = manual_name.strip() if (new_item_toggle or not supplier_items) else p_name
            
            col1, col2 = st.columns(2)
            p_qty = col1.number_input("Quantity Received (Whole Numbers)", min_value=1, step=1)
            p_ref = col2.text_input("Invoice / Document #")
            
            uploaded_file = st.file_uploader("Upload Invoice Photo/PDF", type=['pdf', 'png', 'jpg', 'jpeg'])
            
            if st.form_submit_button("Confirm & Update Warehouse Stock"):
                if not final_name or final_name == "-- Type/Select Item --":
                    st.error("Please provide an Item Name.")
                else:
                    f_path = ""
                    if uploaded_file:
                        f_path = os.path.join("uploads", f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uploaded_file.name}")
                        with open(f_path, "wb") as f:
                            f.write(uploaded_file.getbuffer())
                    
                    # 1. Update Assets (The Warehouse Stock)
                    db.execute("INSERT INTO assets (item_name, qty) VALUES (?, ?) ON CONFLICT(item_name) DO UPDATE SET qty = qty + excluded.qty", (final_name, int(p_qty)))
                    # 2. Update Supplier Memory for next time's prediction
                    db.execute("INSERT OR IGNORE INTO supplier_memory VALUES (?, ?)", (vendor, final_name))
                    # 3. Log the history
                    db.execute("INSERT INTO logs VALUES ('PURCHASE', ?, ?, ?, ?, ?, ?, ?)", (final_name, int(p_qty), p_ref, f_path, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M"), vendor))
                    
                    db.commit()
                    st.success(f"Stock Updated! Warehouse now has +{int(p_qty)} of {final_name}.")
                    st.rerun()

with tab3:
    st.subheader("📤 Record Site Delivery")
    # Only show items that have stock in the warehouse
    items_list = pd.read_sql("SELECT item_name, qty FROM assets WHERE qty > 0", db)
    
    if items_list.empty:
        st.warning("No stock available in the warehouse.")
    else:
        with st.form("delivery_form"):
            d_choice = st.selectbox("Select Item to Deliver", items_list['item_name'].tolist())
            d_bal = items_list[items_list['item_name'] == d_choice]['qty'].values[0]
            st.info(f"Current Warehouse Balance: {int(d_bal)}")
            
            d_qty = st.number_input("Quantity Out", min_value=1, step=1)
            d_site = st.text_input("Project / Site Name")
            
            if st.form_submit_button("Confirm Dispatch"):
                if d_qty > d_bal:
                    st.error(f"Cannot deliver {int(d_qty)}. Only {int(d_bal)} available.")
                else:
                    # Subtract from Warehouse Stock
                    db.execute("UPDATE assets SET qty = qty - ? WHERE item_name = ?", (int(d_qty), d_choice))
                    db.execute("INSERT INTO logs VALUES ('DELIVERY', ?, ?, ?, ?, ?, ?, 'INTERNAL')", (d_choice, int(d_qty), d_site, "", st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M"), "INTERNAL"))
                    db.commit()
                    st.rerun()
