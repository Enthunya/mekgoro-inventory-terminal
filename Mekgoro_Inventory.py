import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime

# --- 1. CONFIG & DATABASE ---
st.set_page_config(page_title="Mekgoro Inventory", layout="wide")
db = sqlite3.connect("mekgoro_database.db", check_same_thread=False)

def init_db():
    # Tables for stock and logs
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty REAL, last_update TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty REAL, ref_no TEXT, user TEXT, timestamp TEXT)")
    db.commit()

    # --- AUTO-LOAD FEATURE ---
    # Check if the database is empty
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM assets")
    if cursor.fetchone()[0] == 0:
        # If empty, try to load your Sage List
        csv_path = "ItemListingReport.csv"
        if os.path.exists(csv_path):
            try:
                # Reading the Sage CSV (skipping the 'sep=,' line)
                df_sage = pd.read_csv(csv_path, skiprows=1)
                # Clean descriptions and set Qty to 0 as requested
                unique_items = df_sage['Description'].dropna().unique()
                for item in unique_items:
                    db.execute("INSERT OR IGNORE INTO assets VALUES (?, 0, ?)",
                               (item, datetime.now().strftime("%Y-%m-%d %H:%M")))
                db.commit()
            except Exception as e:
                pass # Silently fail if file format is wrong on startup

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
st.title(f"🏗️ Mekgoro Terminal | Active User: {st.session_state.user}")
tab1, tab2, tab3 = st.tabs(["📊 Warehouse Ledger", "📥 Receive Stock", "🕒 Activity Logs"])

with tab1:
    st.subheader("Current Stock Levels")
    # Search box for the ledger
    search_query = st.text_input("🔍 Search Inventory (e.g., 'Cable Ties' or 'Cement')", "")
    
    df = pd.read_sql("SELECT * FROM assets ORDER BY item_name ASC", db)
    if search_query:
        df = df[df['item_name'].str.contains(search_query, case=False, na=False)]
    
    st.dataframe(df, use_container_width=True, height=400)
    
    # Manual Export for Ndule
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("📥 Download Report (CSV)", csv, f"Mekgoro_Stock_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv")

with tab2:
    st.subheader("Record Incoming Material")
    # Get all 1,990+ items for the dropdown
    all_items = pd.read_sql("SELECT item_name FROM assets ORDER BY item_name ASC", db)['item_name'].tolist()
    
    with st.form("add_stock_form"):
        # Tshepo can type here to find "Cable Ties" instantly
        item_selection = st.selectbox("Search/Select Material", ["Other (Add New Item)"] + all_items)
        
        new_item_name = ""
        if item_selection == "Other (Add New Item)":
            new_item_name = st.text_input("New Item Name:")
            
        amt = st.number_input("Quantity Received", min_value=0.0, step=1.0)
        ref = st.text_input("Delivery Note / Invoice #")
        
        if st.form_submit_button("Submit Entry"):
            final_name = new_item_name if item_selection == "Other (Add New Item)" else item_selection
            if final_name:
                db.execute("INSERT OR REPLACE INTO assets VALUES (?, (SELECT COALESCE(qty,0) FROM assets WHERE item_name=?) + ?, ?)",
                           (final_name, final_name, amt, datetime.now().strftime("%Y-%m-%d %H:%M")))
                db.execute("INSERT INTO logs VALUES (?, ?, ?, ?, ?, ?)",
                           ("ADD", final_name, amt, ref, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
                db.commit()
                st.success(f"Added {amt} {final_name}")
                st.rerun()

with tab3:
    st.subheader("Recent Activity")
    logs_df = pd.read_sql("SELECT * FROM logs ORDER BY timestamp DESC", db)
    st.table(logs_df.head(50))
