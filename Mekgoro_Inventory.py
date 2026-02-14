import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- 1. CONFIG & DATABASE ---
st.set_page_config(page_title="Mekgoro Inventory", layout="wide")
db = sqlite3.connect("mekgoro_database.db", check_same_thread=False)

def init_db():
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty REAL, last_update TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty REAL, ref_no TEXT, user TEXT, timestamp TEXT)")
    db.commit()

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
    
    # --- SAGE IMPORT TOOL (HANDLES DUPLICATES) ---
    with st.expander("📂 Import from Sage (ItemListingReport.csv)"):
        uploaded_file = st.file_uploader("Upload Sage CSV", type="csv")
        if uploaded_file is not None:
            try:
                # Sage files often have a 'sep=,' header, we skip it
                df_sage = pd.read_csv(uploaded_file, skiprows=1)
                
                # CLEANING: Group by Description and sum 'Qty on Hand'
                cleaned = df_sage.groupby('Description')['Qty on Hand'].sum().reset_index()
                
                st.write(f"✅ Found {len(cleaned)} unique items (Duplicates merged).")
                if st.button("Update Ledger with Sage Data"):
                    for _, row in cleaned.iterrows():
                        db.execute("INSERT OR REPLACE INTO assets VALUES (?, ?, ?)",
                                   (row['Description'], row['Qty on Hand'], datetime.now().strftime("%Y-%m-%d %H:%M")))
                    db.commit()
                    st.success("Ledger updated!")
                    st.rerun()
            except Exception as e:
                st.error(f"Format Error: Ensure you use the 'ItemListingReport.csv' from Sage.")

    # Show Ledger
    df = pd.read_sql("SELECT * FROM assets ORDER BY item_name ASC", db)
    st.dataframe(df, use_container_width=True)

with tab2:
    st.subheader("Record Incoming Material")
    # Fetch items from DB for the dropdown
    existing_items = pd.read_sql("SELECT item_name FROM assets", db)['item_name'].tolist()
    
    with st.form("add_stock_form"):
        # Searchable selectbox for 2000+ items
        item_selection = st.selectbox("Search/Select Material", ["Other (Add New Item)"] + existing_items)
        
        new_item_name = ""
        if item_selection == "Other (Add New Item)":
            new_item_name = st.text_input("New Item Name:")
            
        amt = st.number_input("Quantity Received", min_value=0.0, step=0.1)
        ref = st.text_input("Delivery Note / Receipt #")
        
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
    st.table(logs_df.head(50)) # Show latest 50 logs
