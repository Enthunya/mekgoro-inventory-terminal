import streamlit as st
import pandas as pd
import sqlite3
import os
import io
from datetime import datetime

# --- 1. CONFIG & DATABASE ---
st.set_page_config(page_title="Mekgoro Inventory", layout="wide")
# Moving to v9 for Whole Number Logic
db = sqlite3.connect("mekgoro_v9.db", check_same_thread=False)

def init_db():
    # Use INTEGER for qty to strictly enforce whole numbers
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty INTEGER, last_update TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty INTEGER, ref_no TEXT, user TEXT, timestamp TEXT)")
    db.commit()

    # AUTO-LOAD: Absorbs your Excel/CSV from Sage
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM assets")
    if cursor.fetchone()[0] == 0:
        excel_file = "ItemListingReport.xlsx"
        csv_file = "ItemListingReport.csv"
        df = None
        if os.path.exists(excel_file):
            df = pd.read_excel(excel_file)
        elif os.path.exists(csv_file):
            df = pd.read_csv(csv_file, skiprows=1)

        if df is not None:
            try:
                for _, row in df.iterrows():
                    name = str(row['Description'])
                    # Convert Sage quantity to a whole number immediately
                    initial_qty = int(float(row['Qty on Hand']))
                    db.execute("INSERT OR IGNORE INTO assets VALUES (?, ?, ?)",
                               (name, initial_qty, datetime.now().strftime("%Y-%m-%d %H:%M")))
                db.commit()
            except:
                pass

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
tab1, tab2, tab3, tab4 = st.tabs(["📊 Total Available", "📥 Purchases (Stock IN)", "📤 Deliveries (Stock OUT)", "🕒 History Logs"])

with tab1:
    st.subheader("Current Warehouse Stock Levels")
    search = st.text_input("🔍 Search for an item...", "")
    # Cast to int in display to remove .0
    data = pd.read_sql("SELECT item_name as 'Item Description', CAST(qty AS INT) as 'Total Available' FROM assets ORDER BY item_name ASC", db)
    if search:
        data = data[data['Item Description'].str.contains(search, case=False, na=False)]
    st.dataframe(data, use_container_width=True, height=500)

with tab2:
    st.subheader("📥 Record New Purchases")
    items = pd.read_sql("SELECT item_name FROM assets", db)['item_name'].tolist()
    with st.form("purchase_form"):
        choice = st.selectbox("Select Item Bought", items)
        # Force whole numbers using value=1 and step=1 (Integer mode)
        raw_qty = st.number_input("Quantity Received (Whole Numbers Only)", min_value=1, step=1, value=1)
        ref = st.text_input("Supplier Invoice / Delivery Note #")
        if st.form_submit_button("Add to Inventory"):
            qty_int = int(raw_qty)
            db.execute("UPDATE assets SET qty = qty + ? WHERE item_name = ?", (qty_int, choice))
            db.execute("INSERT INTO logs VALUES ('PURCHASE', ?, ?, ?, ?, ?)", 
                       (choice, qty_int, ref, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
            db.commit()
            st.success(f"Successfully added {qty_int} units of {choice}")
            st.rerun()

with tab3:
    st.subheader("📤 Record Site Deliveries")
    items_df = pd.read_sql("SELECT item_name, qty FROM assets", db)
    with st.form("delivery_form"):
        choice = st.selectbox("Select Item to Deliver", items_df['item_name'].tolist())
        current_bal = int(items_df[items_df['item_name'] == choice]['qty'].values[0])
        st.write(f"📦 **Current Balance in Warehouse: {current_bal}**")
        
        # Force whole numbers for dispatch
        raw_out = st.number_input("Quantity to Dispatch (Whole Numbers Only)", min_value=1, step=1, value=1)
        project = st.text_input("Project Name / Site Address")
        
        if st.form_submit_button("Confirm Dispatch"):
            out_int = int(raw_out)
            if out_int > current_bal:
                st.error(f"❌ Error: Cannot deliver {out_int}. Only {current_bal} available.")
            else:
                db.execute("UPDATE assets SET qty = qty - ? WHERE item_name = ?", (out_int, choice))
                db.execute("INSERT INTO logs VALUES ('DELIVERY', ?, ?, ?, ?, ?)", 
                           (choice, out_int, project, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
                db.commit()
                st.warning(f"Dispatched {out_int} units to {project}")
                st.rerun()

with tab4:
    st.subheader("Recent Activity History")
    logs = pd.read_sql("SELECT timestamp as 'Date/Time', type as 'Action', item_name as 'Item', CAST(qty AS INT) as 'Quantity', ref_no as 'Ref/Project', user as 'Staff' FROM logs ORDER BY timestamp DESC", db)
    st.dataframe(logs, use_container_width=True)
