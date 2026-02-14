import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime

# --- 1. CONFIG & DATABASE ---
st.set_page_config(page_title="Mekgoro Inventory", layout="wide")
# Moving to v10 to ensure a clean slate
db = sqlite3.connect("mekgoro_v10.db", check_same_thread=False)

def init_db():
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty INTEGER, last_update TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty INTEGER, ref_no TEXT, user TEXT, timestamp TEXT)")
    db.commit()

    # AUTO-LOAD FROM FILE
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM assets")
    if cursor.fetchone()[0] == 0:
        # Check for your specific file names
        for f in ["ItemListingReport.csv", "ItemListingReport.xlsx"]:
            if os.path.exists(f):
                try:
                    df = pd.read_excel(f) if f.endswith('.xlsx') else pd.read_csv(f, skiprows=1)
                    # Use exact column names from your Sage file
                    for _, row in df.iterrows():
                        name = str(row['Description'])
                        # Force absolute whole number
                        initial_qty = int(abs(float(row['Qty on Hand'])))
                        db.execute("INSERT OR IGNORE INTO assets VALUES (?, ?, ?)",
                                   (name, initial_qty, datetime.now().strftime("%Y-%m-%d %H:%M")))
                    db.commit()
                    break
                except:
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
    st.subheader("Warehouse Inventory")
    # Diagnostic check
    item_check = pd.read_sql("SELECT COUNT(*) as count FROM assets", db)['count'][0]
    if item_check == 0:
        st.error("🚨 System is empty! Ensure 'ItemListingReport.csv' is uploaded to GitHub.")
    
    search = st.text_input("🔍 Search Inventory", "")
    data = pd.read_sql("SELECT item_name as 'Item', qty as 'Total Available' FROM assets ORDER BY item_name ASC", db)
    if search:
        data = data[data['Item'].str.contains(search, case=False, na=False)]
    st.dataframe(data, use_container_width=True, height=400)

with tab2:
    st.subheader("📥 Record New Purchases")
    items = pd.read_sql("SELECT item_name FROM assets ORDER BY item_name ASC", db)['item_name'].tolist()
    if not items:
        st.warning("No items available to select.")
    else:
        with st.form("in_form"):
            choice = st.selectbox("Item Description", items)
            qty_in = st.number_input("Quantity Received", min_value=1, step=1)
            ref = st.text_input("Supplier Invoice #")
            if st.form_submit_button("Add to Stock"):
                db.execute("UPDATE assets SET qty = qty + ? WHERE item_name = ?", (qty_int := int(qty_in), choice))
                db.execute("INSERT INTO logs VALUES ('PURCHASE', ?, ?, ?, ?, ?)", 
                           (choice, qty_int, ref, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
                db.commit()
                st.success("Updated!")
                st.rerun()

with tab3:
    st.subheader("📤 Record Site Deliveries")
    items_df = pd.read_sql("SELECT item_name, qty FROM assets ORDER BY item_name ASC", db)
    if items_df.empty:
        st.warning("No items available to deliver.")
    else:
        with st.form("out_form"):
            choice = st.selectbox("Select Item", items_df['item_name'].tolist())
            # Safety check to avoid IndexError
            current_row = items_df[items_df['item_name'] == choice]
            current_bal = int(current_row['qty'].values[0]) if not current_row.empty else 0
            
            st.write(f"📦 **Total Available: {current_bal}**")
            qty_out = st.number_input("Quantity to Dispatch", min_value=1, step=1)
            project = st.text_input("Project / Site Name")
            if st.form_submit_button("Confirm Dispatch"):
                if (out_int := int(qty_out)) > current_bal:
                    st.error(f"Insufficient stock! Only {current_bal} available.")
                else:
                    db.execute("UPDATE assets SET qty = qty - ? WHERE item_name = ?", (out_int, choice))
                    db.execute("INSERT INTO logs VALUES ('DELIVERY', ?, ?, ?, ?, ?)", 
                               (choice, out_int, project, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
                    db.commit()
                    st.warning("Dispatched!")
                    st.rerun()

with tab4:
    st.subheader("Activity History")
    logs = pd.read_sql("SELECT timestamp, type as 'Action', item_name, qty as 'Quantity', ref_no as 'Project/Ref', user FROM logs ORDER BY timestamp DESC", db)
    st.dataframe(logs, use_container_width=True)
