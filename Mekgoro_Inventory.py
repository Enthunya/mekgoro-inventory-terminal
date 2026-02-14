import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- 1. CONFIG & DATABASE ---
st.set_page_config(page_title="Mekgoro Inventory", layout="wide")
db = sqlite3.connect("mekgoro_database.db", check_same_thread=False)

def init_db():
    # Setup local tables for assets and logs
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty INTEGER, last_update TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty INTEGER, ref_no TEXT, user TEXT, timestamp TEXT)")
    db.commit()

init_db()

# --- 2. TEAM LOGIN LIST ---
if "user" not in st.session_state:
    st.title("🛡️ Mekgoro Secure Login")
    # Removed generic 'Manager', Ndule is now the lead
    team_list = ["Ndule (Manager)", "Tshepo (Driver)", "Biino", "Anthony", "Mike"]
    name = st.selectbox("Identify yourself:", team_list)
    if st.button("Enter Terminal"):
        st.session_state.user = name
        st.rerun()
    st.stop()

# --- 3. MAIN TERMINAL ---
st.title(f"🏗️ Mekgoro Terminal | Logged in: {st.session_state.user}")
tab1, tab2, tab3 = st.tabs(["📊 Warehouse Ledger", "📥 Receive Stock", "🕒 Activity Logs"])

with tab1:
    st.subheader("Current Stock Levels")
    df = pd.read_sql("SELECT * FROM assets", db)
    
    if df.empty:
        st.info("The ledger is currently empty.")
    else:
        st.dataframe(df, use_container_width=True)
        
        # Manual Backup Button for Ndule
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Inventory Report (CSV)",
            data=csv,
            file_name=f"Mekgoro_Stock_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )

with tab2:
    st.subheader("Record Incoming Materials")
    with st.form("add_stock"):
        item = st.selectbox("Item Description", ["Cement 50kg", "Sand (m3)", "Stone (m3)", "Brick (Qty)"])
        amt = st.number_input("Quantity Received", min_value=1)
        ref = st.text_input("Delivery Note / Ref Number", placeholder="e.g. DN-101")
        
        if st.form_submit_button("Record Entry"):
            # Update local inventory levels
            db.execute("INSERT OR REPLACE INTO assets VALUES (?, (SELECT COALESCE(qty,0) FROM assets WHERE item_name=?) + ?, ?)",
                       (item, item, amt, datetime.now().strftime("%Y-%m-%d %H:%M")))
            
            # Log the action with the reference number
            db.execute("INSERT INTO logs VALUES (?, ?, ?, ?, ?, ?)",
                       ("ADD", item, amt, ref, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
            db.commit()
            st.success(f"Recorded {amt} {item}. Logged by {st.session_state.user}")
            st.rerun()

with tab3:
    st.subheader("Audit Trail")
    logs_df = pd.read_sql("SELECT * FROM logs ORDER BY timestamp DESC", db)
    st.table(logs_df)
