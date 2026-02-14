import streamlit as st
import pandas as pd
import sqlite3
import os
import io
from datetime import datetime

# --- 1. CONFIG & DATABASE ---
st.set_page_config(page_title="Mekgoro Inventory", layout="wide")
# Moving to v10 for safety checks and better loading
db = sqlite3.connect("mekgoro_v10.db", check_same_thread=False)

def init_db():
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty INTEGER, last_update TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty INTEGER, ref_no TEXT, user TEXT, timestamp TEXT)")
    db.commit()

    # AUTO-LOAD LOGIC
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM assets")
    if cursor.fetchone()[0] == 0:
        # Check for both possible extensions
        files_to_check = ["ItemListingReport.xlsx", "ItemListingReport.csv"]
        for f in files_to_check:
            if os.path.exists(f):
                try:
                    if f.endswith('.xlsx'):
                        df = pd.read_excel(f)
                    else:
                        df = pd.read_csv(f, skiprows=1)
                    
                    # Ensure we have the right columns
                    if 'Description' in df.columns and 'Qty on Hand' in df.columns:
                        for _, row in df.iterrows():
                            name = str(row['Description'])
                            # Round to whole number
                            initial_qty = int(float(row['Qty on Hand']))
                            db.execute("INSERT OR IGNORE INTO assets VALUES (?, ?, ?)",
                                       (name, initial_qty, datetime.now().strftime("%Y-%m-%d %H:%M")))
                        db.commit()
                        break
                except Exception as e:
                    continue

init_db()

# --- 2. LOGIN ---
if "user" not in st.session_state:
    st.title("🛡️ Mekgoro Secure Login")
    name = st.selectbox("Who is logging in?", ["Ndule", "Tshepo (Driver)", "Biino", "Anthony", "Mike"])
    if st.button("Access Terminal"):
        st.session_state.user = name
        st.rerun()
    st.stop()

# --- 3. TABS ---
st.title(f"🏗️ Mekgoro Terminal | User: {st.session_state.user}")
tab1, tab2, tab3, tab4 = st.tabs(["📊 Total Available", "📥 Purchases", "📤 Deliveries", "🕒 History"])

with tab1:
    st.subheader("Current Warehouse Stock Levels")
    
    # DIAGNOSTIC TOOL: Only shows if the database is empty
    items_count = pd.read_sql("SELECT COUNT(*) as count FROM assets", db)['count'][0]
    if items_count == 0:
        st.error("🚨 NO ITEMS LOADED. The app cannot find 'ItemListingReport.xlsx' or '.csv' in your GitHub folder.")
        st.info("Please make sure the file name is EXACTLY 'ItemListingReport.xlsx' (case sensitive) and it is in the same folder as this code.")
        if st.checkbox("Show files in current folder"):
            st.write(os.listdir("."))

    search = st.text_input("🔍 Search for an item...", "")
    data = pd.read_sql("SELECT item_name as 'Item Description', CAST(qty AS INT) as 'Total Available' FROM assets ORDER BY item_name ASC", db)
    if search:
        data = data[data['Item Description'].str.contains(search, case=False, na=False)]
    st.dataframe(data, use_container_width=True, height=500)

with tab2:
    st.subheader("📥 Record New Purchases")
    all_items = pd.read_sql("SELECT item_name FROM assets ORDER BY item_name ASC", db)['item_name'].tolist()
    
    if not all_items:
        st.warning("Cannot add stock: No items found in the system.")
    else:
        with st.form("purchase_form"):
            choice = st.selectbox("Select Item Bought", all_items)
            raw_qty = st.number_input("Quantity Received (Whole Number)", min_value=1, step=1, value=1)
            ref = st.text_input("Supplier Invoice #")
            submit = st.form_submit_button("Add to Inventory")
            if submit:
                qty_int = int(raw_qty)
                db.execute("UPDATE assets SET qty = qty + ? WHERE item_name = ?", (qty_int, choice))
                db.execute("INSERT INTO logs VALUES ('PURCHASE', ?, ?, ?, ?, ?)", 
                           (choice, qty_int, ref, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
                db.commit()
                st.success(f"Added {qty_int} units.")
                st.rerun()

with tab3:
    st.subheader("📤 Record Site Deliveries")
    items_df = pd.read_sql("SELECT item_name, qty FROM assets ORDER BY item_name ASC", db)
    
    if items_df.empty:
        st.warning("Cannot record delivery: No items found in the system.")
    else:
        with st.form("delivery_form"):
            choice = st.selectbox("Select Item to Deliver", items_df['item_name'].tolist())
            
            # SAFE LOOKUP: Check if choice exists before getting index 0
            selected_row = items_df[items_df['item_name'] == choice]
            current_bal = int(selected_row['qty'].values[0]) if not selected_row.empty else 0
            
            st.write(f"📦 **Current Balance in Warehouse: {current_bal}**")
            raw_out = st.number_input("Quantity to Dispatch (Whole Number)", min_value=1, step=1, value=1)
            project = st.text_input("Project Name / Site Address")
            submit = st.form_submit_button("Confirm Dispatch")
            
            if submit:
                out_int = int(raw_out)
                if out_int > current_bal:
                    st.error(f"❌ Error: Only {current_bal} available.")
                else:
                    db.execute("UPDATE assets SET qty = qty - ? WHERE item_name = ?", (out_int, choice))
                    db.execute("INSERT INTO logs VALUES ('DELIVERY', ?, ?, ?, ?, ?)", 
                               (choice, out_int, project, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
                    db.commit()
                    st.warning(f"Dispatched {out_int} units.")
                    st.rerun()

with tab4:
    st.subheader("Recent Activity History")
    logs = pd.read_sql("SELECT timestamp as 'Date/Time', type as 'Action', item_name as 'Item', CAST(qty AS INT) as 'Quantity', ref_no as 'Ref/Project', user as 'Staff' FROM logs ORDER BY timestamp DESC", db)
    st.dataframe(logs, use_container_width=True)
