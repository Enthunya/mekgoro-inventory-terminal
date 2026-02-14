import streamlit as st
import pandas as pd
import sqlite3
import os
import io
from datetime import datetime

# --- 1. CONFIG & DATABASE ---
st.set_page_config(page_title="Mekgoro Inventory", layout="wide")
# Moving to v8 for the final terminology and log fix
db = sqlite3.connect("mekgoro_v8.db", check_same_thread=False)

def init_db():
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty REAL, last_update TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty REAL, ref_no TEXT, user TEXT, timestamp TEXT)")
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
                    initial_qty = float(row['Qty on Hand'])
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
    data = pd.read_sql("SELECT item_name as 'Item Description', qty as 'Total Available' FROM assets ORDER BY item_name ASC", db)
    if search:
        data = data[data['Item Description'].str.contains(search, case=False, na=False)]
    st.dataframe(data, use_container_width=True, height=500)

with tab2:
    st.subheader("📥 Record New Purchases")
    st.info("Use this when we buy items and they arrive at the warehouse.")
    items = pd.read_sql("SELECT item_name FROM assets", db)['item_name'].tolist()
    with st.form("purchase_form"):
        choice = st.selectbox("Select Item Bought", items)
        raw_qty = st.number_input("Quantity Received", min_value=0.0, step=1.0)
        ref = st.text_input("Supplier Invoice / Delivery Note #")
        if st.form_submit_button("Add to Inventory"):
            clean_qty = abs(raw_qty)
            db.execute("UPDATE assets SET qty = qty + ? WHERE item_name = ?", (clean_qty, choice))
            # Logs now show absolute numbers only
            db.execute("INSERT INTO logs VALUES ('PURCHASE', ?, ?, ?, ?, ?)", 
                       (choice, clean_qty, ref, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
            db.commit()
            st.success(f"Successfully added {clean_qty} units of {choice}")
            st.rerun()

with tab3:
    st.subheader("📤 Record Site Deliveries")
    st.info("Use this when Tshepo takes items out for delivery to a project.")
    items_df = pd.read_sql("SELECT item_name, qty FROM assets", db)
    with st.form("delivery_form"):
        choice = st.selectbox("Select Item to Deliver", items_df['item_name'].tolist())
        
        # Show availability right here so they don't have to switch tabs
        current_bal = items_df[items_df['item_name'] == choice]['qty'].values[0]
        st.write(f"📦 **Current Balance in Warehouse: {current_bal}**")
        
        raw_out = st.number_input("Quantity to Dispatch", min_value=0.0, step=1.0)
        project = st.text_input("Project Name / Site Address")
        
        if st.form_submit_button("Confirm Dispatch"):
            clean_out = abs(raw_out)
            if clean_out > current_bal:
                st.error(f"❌ Error: Cannot deliver {clean_out}. Only {current_bal} available.")
            else:
                db.execute("UPDATE assets SET qty = qty - ? WHERE item_name = ?", (clean_out, choice))
                # Logs show absolute number (positive) but type is 'DELIVERY'
                db.execute("INSERT INTO logs VALUES ('DELIVERY', ?, ?, ?, ?, ?)", 
                           (choice, clean_out, project, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
                db.commit()
                st.warning(f"Dispatched {clean_out} units to {project}")
                st.rerun()

with tab4:
    st.subheader("Recent Activity History")
    # Clean logs for Ndule to review
    logs = pd.read_sql("SELECT timestamp as 'Date/Time', type as 'Action', item_name as 'Item', qty as 'Quantity', ref_no as 'Ref/Project', user as 'Staff' FROM logs ORDER BY timestamp DESC", db)
    st.dataframe(logs, use_container_width=True)
