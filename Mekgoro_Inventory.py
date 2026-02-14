import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- 1. CONFIG & DATABASE REPAIR ---
st.set_page_config(page_title="Mekgoro Inventory Terminal", layout="wide")
db = sqlite3.connect("mekgoro_database.db", check_same_thread=False)

def init_db():
    # Ensures tables are ready and prevents 'OperationalError'
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty INTEGER, last_update TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty INTEGER, user TEXT, timestamp TEXT)")
    db.commit()

init_db()

# --- 2. GOOGLE DRIVE AUTHENTICATION ---
if "gcp_service_account" in st.secrets:
    try:
        info = dict(st.secrets["gcp_service_account"])
        # Fixes the 'ValueError' by cleaning the key format
        info["private_key"] = info["private_key"].replace("\\n", "\n")
        
        credentials = service_account.Credentials.from_service_account_info(
            info, scopes=['https://www.googleapis.com/auth/drive.file']
        )
        drive_service = build('drive', 'v3', credentials=credentials)
    except Exception as e:
        st.error(f"❌ Google Connection Failed: {e}")
        st.stop()
else:
    st.warning("⚠️ Waiting for Secrets... Please add them in the Streamlit Dashboard Settings.")
    st.stop()

# --- 3. LOGIN SYSTEM ---
if "user" not in st.session_state:
    st.title("🛡️ Mekgoro Secure Login")
    user_list = ["Manager", "Biino", "Anthony", "Mike"]
    name = st.selectbox("Select User:", user_list)
    if st.button("Access Terminal"):
        st.session_state.user = name
        st.rerun()
    st.stop()

# --- 4. MAIN INTERFACE ---
st.title(f"🏗️ Mekgoro Terminal | User: {st.session_state.user}")
tab1, tab2, tab3 = st.tabs(["📊 Inventory Status", "📥 Add Stock", "🕒 Activity Logs"])

with tab1:
    st.subheader("Current Warehouse Levels")
    df = pd.read_sql("SELECT * FROM assets", db)
    if df.empty:
        st.info("No stock recorded yet.")
    else:
        st.dataframe(df, use_container_width=True)

with tab2:
    st.subheader("Receive New Items")
    with st.form("add_form"):
        item = st.selectbox("Item", ["Cement 50kg", "Sand (Cubic m)", "Stone (Cubic m)"])
        amt = st.number_input("Quantity Received", min_value=1)
        if st.form_submit_button("Record Entry"):
            # Update Database
            db.execute("INSERT OR REPLACE INTO assets VALUES (?, (SELECT COALESCE(qty,0) FROM assets WHERE item_name=?) + ?, ?)",
                       (item, item, amt, datetime.now().strftime("%Y-%m-%d %H:%M")))
            # Log Activity
            db.execute("INSERT INTO logs VALUES (?, ?, ?, ?, ?)",
                       ("ADD", item, amt, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
            db.commit()
            st.success(f"Added {amt} of {item}!")
            st.rerun()

with tab3:
    st.subheader("Recent Activity")
    logs_df = pd.read_sql("SELECT * FROM logs ORDER BY timestamp DESC", db)
    st.table(logs_df)

