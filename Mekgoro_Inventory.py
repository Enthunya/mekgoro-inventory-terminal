import streamlit as st
import pandas as pd
import sqlite3
import os
import io
from datetime import datetime

# --- 1. CONFIG & DATABASE ---
st.set_page_config(page_title="Mekgoro Inventory", layout="wide")
# We use v4 to ensure a completely fresh start with your Sage data
db = sqlite3.connect("mekgoro_v4.db", check_same_thread=False)

def init_db():
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty REAL, last_update TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty REAL, ref_no TEXT, user TEXT, timestamp TEXT)")
    db.commit()

    # --- AUTO-LOAD BASE FROM SAGE ---
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM assets")
    if cursor.fetchone()[0] == 0:
        # We check for the CSV or Excel file you downloaded from Sage
        base_files = ["ItemListingReport.csv", "ItemListingReport.xlsx", "Cleaned_Sage_Inventory.csv"]
        for f in base_files:
            if os.path.exists(f):
                try:
                    # Handle different file types
                    if f.endswith('.csv'):
                        # Sage CSVs usually have a 'sep=,' line we need to skip
                        df = pd.read_csv(f, skiprows=1 if "Listing" in f else 0)
                    else:
                        df = pd.read_excel(f)
                    
                    # Identify the correct columns (Sage uses 'Description' and 'Qty on Hand')
                    item_col = 'Description' if 'Description' in df.columns else df.columns[1]
                    qty_col = 'Qty on Hand' if 'Qty on Hand' in df.columns else df.columns[-3] # Usually near the end
                    
                    # Clean and Insert
                    cleaned = df.groupby(item_col)[qty_col].sum().reset_index()
                    for _, row in cleaned.iterrows():
                        db.execute("INSERT OR IGNORE INTO assets VALUES (?, ?, ?)",
                                   (str(row[item_col]), float(row[qty_col]), datetime.now().strftime("%Y-%m-%d %H:%M")))
                    db.commit()
                    break # Success!
                except Exception as e:
                    continue

init_db()

# --- 2. TEAM LOGIN ---
if "user" not in st.session_state:
    st.title("🛡️ Mekgoro Secure Login")
    team_list = ["Ndule", "Tshepo (Driver)", "Biino", "Anthony", "Mike"]
    name = st.selectbox("Who is logging in?", team_list)
    if st.button("Access Terminal"):
        st.session_state.user = name
        st.rerun()
    st.stop()

# --- 3. MAIN TERMINAL ---
st.title(f"🏗️ Mekgoro Terminal | User: {st.session_state.user}")
tab1, tab2, tab3 = st.tabs(["📊 Warehouse Ledger", "📥 Receive Stock", "🕒 Activity Logs"])

with tab1:
    st.subheader("Current Stock Levels")
    
    # Check if the list loaded
    df_check = pd.read_sql("SELECT COUNT(*) as count FROM assets", db)
    item_count = df_check['count'].iloc[0]
    
    if item_count == 0:
        st.warning("⚠️ No items found. Please upload 'ItemListingReport.csv' to GitHub and refresh.")
    else:
        st.success(f"✅ System active with {item_count} items from Sage.")

    search_query = st.text_input("🔍 Search Inventory (Type here to find items)", "")
    df = pd.read_sql("SELECT item_name as 'Item', qty as 'Qty' FROM assets ORDER BY item_name ASC", db)
    
    if search_query:
        df = df[df['Item'].str.contains(search_query, case=False, na=False)]
    
    st.dataframe(df, use_container_width=True, height=400)

with tab2:
    st.subheader("Record Incoming Material")
    # This list is now powered by your Sage Excel/CSV file
    all_items = pd.read_sql("SELECT item_name FROM assets ORDER BY item_name ASC", db)['item_name'].tolist()
    
    st.info("Search for the item below. If it's a brand new item not in Sage, use the 'Manual' box.")
    
    # 1. Search Existing Sage Items
    with st.form("receive_stock"):
        item_selection = st.selectbox("Search Sage Items", all_items)
        amt = st.number_input("Quantity Received", min_value=0.0, step=1.0)
        ref = st.text_input("Delivery Note / Invoice #")
        if st.form_submit_button("Update Stock"):
            db.execute("INSERT OR REPLACE INTO assets VALUES (?, (SELECT qty FROM assets WHERE item_name=?) + ?, ?)",
                       (item_selection, item_selection, amt, datetime.now().strftime("%Y-%m-%d %H:%M")))
            db.execute("INSERT INTO logs VALUES (?, ?, ?, ?, ?, ?)",
                       ("ADD", item_selection, amt, ref, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
            db.commit()
            st.success(f"Added {amt} to {item_selection}")
            st.rerun()

    # 2. Manual Add for New Items
    with st.expander("➕ Add an item not in Sage"):
        with st.form("manual_add"):
            new_name = st.text_input("New Item Name")
            new_qty = st.number_input("Starting Qty", min_value=0.0)
            if st.form_submit_button("Create Item"):
                db.execute("INSERT OR IGNORE INTO assets VALUES (?, ?, ?)", (new_name, new_qty, datetime.now().strftime("%Y-%m-%d %H:%M")))
                db.commit()
                st.rerun()

with tab3:
    st.subheader("Recent Activity")
    logs_df = pd.read_sql("SELECT timestamp as 'Time', user as 'Staff', item_name as 'Item', qty as 'Qty', ref_no as 'Ref' FROM logs ORDER BY timestamp DESC", db)
    st.table(logs_df.head(20))
