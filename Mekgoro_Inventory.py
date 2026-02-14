import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- 1. CONFIG & DATABASE SETUP ---
st.set_page_config(page_title="Mekgoro Inventory", layout="wide")
db = sqlite3.connect("mekgoro_database.db", check_same_thread=False)

def init_db():
    # Creates local storage for stock and transaction history
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty INTEGER, last_update TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty INTEGER, ref_no TEXT, user TEXT, timestamp TEXT)")
    db.commit()

init_db()

# --- 2. TEAM LOGIN ---
if "user" not in st.session_state:
    st.title("🛡️ Mekgoro Secure Login")
    # Ndule is now the lead, Manager removed
    team_list = ["Ndule", "Tshepo (Driver)", "Biino", "Anthony", "Mike"]
    name = st.selectbox("Who is logging in?", team_list)
    if st.button("Access Terminal"):
        st.session_state.user = name
        st.rerun()
    st.stop()

# --- 3. MAIN TERMINAL INTERFACE ---
st.title(f"🏗️ Mekgoro Terminal | Active User: {st.session_state.user}")
tab1, tab2, tab3 = st.tabs(["📊 Warehouse Ledger", "📥 Receive Stock", "🕒 Activity Logs"])

with tab1:
    st.subheader("Current Stock Levels")
    df = pd.read_sql("SELECT * FROM assets", db)
    
    if df.empty:
        st.info("Inventory is currently empty. Record a delivery to see data here.")
    else:
        st.dataframe(df, use_container_width=True)
        
        # Manual CSV Backup for Ndule's records
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Stock Report (CSV)",
            data=csv,
            file_name=f"Mekgoro_Inventory_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )

with tab2:
    st.subheader("Record Incoming Material")
    with st.form("add_stock_form"):
        item = st.selectbox("Select Material", ["Cement 50kg", "Sand (m3)", "Stone (m3)", "Brick (Qty)"])
        amt = st.number_input("Quantity Received", min_value=1, step=1)
        ref = st.text_input("Delivery Note / Invoice #", placeholder="Enter reference number")
        
        if st.form_submit_button("Submit to Inventory"):
            # Logic to add to current stock
            db.execute("INSERT OR REPLACE INTO assets VALUES (?, (SELECT COALESCE(qty,0) FROM assets WHERE item_name=?) + ?, ?)",
                       (item, item, amt, datetime.now().strftime("%Y-%m-%d %H:%M")))
            
            # Log the specific transaction with user and ref number
            db.execute("INSERT INTO logs VALUES (?, ?, ?, ?, ?, ?)",
                       ("ADD", item, amt, ref, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
            db.commit()
            st.success(f"Successfully added {amt} {item}. Entry logged by {st.session_state.user}.")
            st.rerun()

with tab3:
    st.subheader("Transaction History")
    logs_df = pd.read_sql("SELECT * FROM logs ORDER BY timestamp DESC", db)
    if logs_df.empty:
        st.write("No logs available yet.")
    else:
        st.table(logs_df)
