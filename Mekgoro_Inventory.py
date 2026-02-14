import streamlit as st
import pandas as pd
import sqlite3
import os
import io
from datetime import datetime

# --- 1. CONFIG & DATABASE ---
st.set_page_config(page_title="Mekgoro Inventory", layout="wide")
# We move to v5 to trigger a fresh import of your Excel data
db = sqlite3.connect("mekgoro_v5.db", check_same_thread=False)

def init_db():
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty REAL, last_update TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty REAL, ref_no TEXT, user TEXT, timestamp TEXT)")
    db.commit()

    # --- AUTO-LOAD FROM EXCEL OR CSV ---
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM assets")
    if cursor.fetchone()[0] == 0:
        # The app looks for these exact names on your GitHub
        excel_file = "ItemListingReport.xlsx"
        csv_file = "ItemListingReport.csv"
        
        df = None
        if os.path.exists(excel_file):
            df = pd.read_excel(excel_file)
        elif os.path.exists(csv_file):
            df = pd.read_csv(csv_file, skiprows=1)

        if df is not None:
            try:
                # Sage standard columns are 'Description' and 'Qty on Hand'
                # We use these to build your base inventory
                for _, row in df.iterrows():
                    name = str(row['Description'])
                    initial_qty = float(row['Qty on Hand'])
                    db.execute("INSERT OR IGNORE INTO assets VALUES (?, ?, ?)",
                               (name, initial_qty, datetime.now().strftime("%Y-%m-%d %H:%M")))
                db.commit()
            except Exception as e:
                st.error(f"Error reading file columns: {e}")

init_db()

# --- 2. TEAM LOGIN ---
if "user" not in st.session_state:
    st.title("🛡️ Mekgoro Secure Login")
    name = st.selectbox("Who is logging in?", ["Ndule", "Tshepo (Driver)", "Biino", "Anthony", "Mike"])
    if st.button("Access Terminal"):
        st.session_state.user = name
        st.rerun()
    st.stop()

# --- 3. MAIN TERMINAL ---
st.title(f"🏗️ Mekgoro Terminal | User: {st.session_state.user}")
tab1, tab2, tab3, tab4 = st.tabs(["📊 Ledger", "📥 Stock IN", "📤 Stock OUT", "🕒 Logs"])

with tab1:
    st.subheader("Warehouse Inventory")
    search = st.text_input("🔍 Search Sage Items", "")
    data = pd.read_sql("SELECT item_name as 'Item', qty as 'Stock Level' FROM assets ORDER BY item_name ASC", db)
    if search:
        data = data[data['Item'].str.contains(search, case=False, na=False)]
    st.dataframe(data, use_container_width=True, height=400)

with tab2:
    st.subheader("Receive Stock (Tshepo)")
    items = pd.read_sql("SELECT item_name FROM assets", db)['item_name'].tolist()
    with st.form("in_form"):
        choice = st.selectbox("Select Item", items)
        add_qty = st.number_input("Quantity Received", min_value=0.0)
        ref = st.text_input("Delivery Note / Invoice #")
        if st.form_submit_button("Confirm Arrival"):
            db.execute("UPDATE assets SET qty = qty + ?, last_update = ? WHERE item_name = ?", (add_qty, datetime.now().strftime("%Y-%m-%d %H:%M"), choice))
            db.execute("INSERT INTO logs VALUES ('IN', ?, ?, ?, ?, ?)", (choice, add_qty, ref, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
            db.commit()
            st.success("Stock Updated!")
            st.rerun()

with tab3:
    st.subheader("Issue Stock (Project Delivery)")
    items = pd.read_sql("SELECT item_name FROM assets", db)['item_name'].tolist()
    with st.form("out_form"):
        choice = st.selectbox("Select Item to Remove", items)
        rem_qty = st.number_input("Quantity Leaving Warehouse", min_value=0.0)
        project = st.text_input("Project Name / Client Name")
        if st.form_submit_button("Confirm Dispatch"):
            db.execute("UPDATE assets SET qty = qty - ?, last_update = ? WHERE item_name = ?", (rem_qty, datetime.now().strftime("%Y-%m-%d %H:%M"), choice))
            db.execute("INSERT INTO logs VALUES ('OUT', ?, ?, ?, ?, ?)", (choice, rem_qty, project, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
            db.commit()
            st.warning(f"Issued {rem_qty} to {project}")
            st.rerun()

with tab4:
    st.subheader("Activity History")
    logs = pd.read_sql("SELECT timestamp, type, item_name, qty, ref_no as 'Ref/Project', user FROM logs ORDER BY timestamp DESC", db)
    st.table(logs.head(20))
