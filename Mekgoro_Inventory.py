import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime

# --- 1. CONFIG & DATABASE ---
st.set_page_config(page_title="Mekgoro Inventory", layout="wide")
db = sqlite3.connect("mekgoro_database.db", check_same_thread=False)

def init_db():
    # This creates the inventory tables locally on the server
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty INTEGER, last_update TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty INTEGER, user TEXT, timestamp TEXT)")
    db.commit()

init_db()

# --- 2. LOGIN SYSTEM (NO GOOGLE NEEDED) ---
if "user" not in st.session_state:
    st.title("🛡️ Mekgoro Secure Login")
    name = st.selectbox("Who is logging in?", ["Manager", "Biino", "Anthony", "Mike"])
    if st.button("Access Terminal"):
        st.session_state.user = name
        st.rerun()
    st.stop()

# --- 3. MAIN TERMINAL ---
st.title(f"🏗️ Mekgoro Terminal | User: {st.session_state.user}")
tab1, tab2, tab3 = st.tabs(["📊 Inventory Status", "📥 Receive Stock", "🕒 Activity Logs"])

with tab1:
    st.subheader("Warehouse Levels")
    df = pd.read_sql("SELECT * FROM assets", db)
    if df.empty:
        st.info("No stock recorded yet. Use the 'Receive Stock' tab to start.")
    else:
        st.dataframe(df, use_container_width=True)

with tab2:
    st.subheader("Record Incoming Materials")
    with st.form("add_stock"):
        item = st.selectbox("Item Name", ["Cement 50kg", "Sand (m3)", "Stone (m3)", "Brick (Qty)"])
        amt = st.number_input("Quantity Received", min_value=1)
        if st.form_submit_button("Submit to Ledger"):
            # Update the local database
            db.execute("INSERT OR REPLACE INTO assets VALUES (?, (SELECT COALESCE(qty,0) FROM assets WHERE item_name=?) + ?, ?)",
                       (item, item, amt, datetime.now().strftime("%Y-%m-%d %H:%M")))
            db.execute("INSERT INTO logs VALUES (?, ?, ?, ?, ?)",
                       ("ADD", item, amt, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
            db.commit()
            st.success(f"Successfully added {amt} {item} to inventory!")
            st.rerun()

with tab3:
    st.subheader("Recent Activity")
    logs_df = pd.read_sql("SELECT * FROM logs ORDER BY timestamp DESC", db)
    st.table(logs_df)
