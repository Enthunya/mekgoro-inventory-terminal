import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- 1. CONFIG & DATABASE REPAIR ---
st.set_page_config(page_title="Mekgoro Inventory", layout="wide")
db = sqlite3.connect("mekgoro_database.db", check_same_thread=False)

def init_db():
    # Fixes 'OperationalError' by ensuring tables are ready
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty INTEGER, last_update TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty INTEGER, user TEXT, timestamp TEXT)")
    db.commit()

init_db()

# --- 2. GOOGLE DRIVE AUTH (PEM FIX) ---
if "gcp_service_account" in st.secrets:
    try:
        info = dict(st.secrets["gcp_service_account"])
        # THE FIX: This converts the double backslashes back to real breaks for Google
        info["private_key"] = info["private_key"].replace("\\n", "\n")
        
        credentials = service_account.Credentials.from_service_account_info(
            info, scopes=['https://www.googleapis.com/auth/drive.file']
        )
        drive_service = build('drive', 'v3', credentials=credentials)
    except Exception as e:
        st.error(f"❌ Google Connection Failed: {e}")
        st.stop()
else:
    st.warning("⚠️ Secrets missing! Add them in Streamlit Dashboard Settings.")
    st.stop()

# --- 3. LOGIN & TABS ---
if "user" not in st.session_state:
    st.title("🛡️ Mekgoro Secure Login")
    name = st.selectbox("Select User:", ["Manager", "Biino", "Anthony", "Mike"])
    if st.button("Enter Terminal"):
        st.session_state.user = name
        st.rerun()
    st.stop()

st.title(f"🏗️ Mekgoro Terminal | User: {st.session_state.user}")
tab1, tab2 = st.tabs(["📊 Current Stock", "📥 Add Stock"])

with tab1:
    df = pd.read_sql("SELECT * FROM assets", db)
    st.dataframe(df, use_container_width=True)

with tab2:
    with st.form("add_stock"):
        item = st.selectbox("Item", ["Cement 50kg", "Sand", "Stone"])
        amt = st.number_input("Quantity Received", min_value=1)
        if st.form_submit_button("Submit Entry"):
            db.execute("INSERT OR REPLACE INTO assets VALUES (?, (SELECT COALESCE(qty,0) FROM assets WHERE item_name=?) + ?, ?)",
                       (item, item, amt, datetime.now().strftime("%Y-%m-%d %H:%M")))
            db.commit()
            st.success(f"Successfully recorded {amt} of {item}")
            st.rerun()
