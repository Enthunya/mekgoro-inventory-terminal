import streamlit as st
import pandas as pd
import sqlite3
import os
import io
from datetime import datetime
from PIL import Image
import pytesseract

# --- 1. CONFIG & REPAIRABLE DATABASE ---
st.set_page_config(page_title="Mekgoro Inventory", layout="wide")
# Using a versioned DB name to ensure a fresh start if needed
db = sqlite3.connect("mekgoro_v2.db", check_same_thread=False)

def init_db():
    # Create tables if they don't exist
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty REAL, last_update TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty REAL, ref_no TEXT, user TEXT, timestamp TEXT)")
    
    # DATABASE REPAIR: Add 'ref_no' to logs if it's missing from an old version
    try:
        db.execute("ALTER TABLE logs ADD COLUMN ref_no TEXT")
    except:
        pass # Column already exists
        
    db.commit()

    # AUTO-LOAD: Pre-fills items from your Sage list at 0 stock
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM assets")
    if cursor.fetchone()[0] == 0:
        # Look for the cleaned file we generated
        for file_name in ["Cleaned_Sage_Inventory.csv", "ItemListingReport.csv"]:
            if os.path.exists(file_name):
                try:
                    df_clean = pd.read_csv(file_name, skiprows=1 if "Listing" in file_name else 0)
                    col_name = 'Description' if 'Listing' in file_name else 'Item Description'
                    unique_items = df_clean[col_name].dropna().unique()
                    for item in unique_items:
                        db.execute("INSERT OR IGNORE INTO assets VALUES (?, 0, ?)",
                                   (item, datetime.now().strftime("%Y-%m-%d %H:%M")))
                    db.commit()
                    break
                except:
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
    search_query = st.text_input("🔍 Search Inventory", "")
    
    # Safely read the database
    df = pd.read_sql("SELECT item_name as 'Item Description', qty as 'Quantity', last_update as 'Last Updated' FROM assets ORDER BY item_name ASC", db)
    
    if search_query:
        df = df[df['Item Description'].str.contains(search_query, case=False, na=False)]
    
    st.dataframe(df, use_container_width=True, height=400)
    
    # Download as Excel for Ndule
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Inventory')
    st.download_button("📥 Download as Excel", buffer.getvalue(), f"Mekgoro_Stock_{datetime.now().strftime('%Y%m%d')}.xlsx")

with tab2:
    st.subheader("Record Incoming Material")
    all_items = pd.read_sql("SELECT item_name FROM assets ORDER BY item_name ASC", db)['item_name'].tolist()
    
    with st.form("add_stock_form"):
        item_selection = st.selectbox("Search/Select Material", ["Other (Add New Item)"] + all_items)
        new_item_name = st.text_input("New Item Name:") if item_selection == "Other (Add New Item)" else ""
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
    try:
        logs_df = pd.read_sql("SELECT timestamp as 'Time', user as 'Staff', item_name as 'Item', qty as 'Qty', ref_no as 'Ref' FROM logs ORDER BY timestamp DESC", db)
        st.table(logs_df.head(50))
    except:
        st.info("No logs recorded yet.")
