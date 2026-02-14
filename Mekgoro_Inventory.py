import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build

# --- 1. CONFIG & AUTO-REPAIR DATABASE ---
st.set_page_config(page_title="Mekgoro Terminal", layout="wide")
db = sqlite3.connect("mekgoro_database.db", check_same_thread=False)

def init_db():
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty INTEGER, last_update TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty INTEGER, user TEXT, timestamp TEXT)")
    db.commit()

init_db()

# --- 2. GOOGLE DRIVE AUTH (ROBUST VERSION) ---
if "gcp_service_account" in st.secrets:
    try:
        # Convert Secrets to a normal dictionary
        info = dict(st.secrets["gcp_service_account"])
        
        # FIX: Replace double backslashes with actual newlines so Google can read the PEM
        info["private_key"] = info["private_key"].replace("\\n", "\n")
        
        credentials = service_account.Credentials.from_service_account_info(
            info, scopes=['https://www.googleapis.com/auth/drive.file']
        )
        drive_service = build('drive', 'v3', credentials=credentials)
    except Exception as e:
        st.error(f"❌ Google Connection Failed: {e}")
        st.stop()
else:
    st.warning("⚠️ Secrets not detected. Please add them in the Streamlit Settings.")
    st.stop()

# --- 3. LOGIN & INTERFACE ---
if "user" not in st.session_state:
    st.title("🛡️ Mekgoro Secure Login")
    name = st.selectbox("Who is logging in?", ["Manager", "Biino", "Anthony", "Mike"])
    if st.button("Access Terminal"):
        st.session_state.user = name
        st.rerun()
    st.stop()

st.title(f"🏗️ Mekgoro Terminal | User: {st.session_state.user}")
tab1, tab2 = st.tabs(["📊 Inventory Status", "📥 Add Stock"])

with tab1:
    df = pd.read_sql("SELECT * FROM assets", db)
    st.dataframe(df, use_container_width=True)

with tab2:
    with st.form("entry_form"):
        item = st.selectbox("Item", ["Cement 50kg", "Sand", "Stone"])
        amt = st.number_input("Quantity", min_value=1)
        if st.form_submit_button("Record"):
            # Update DB
            db.execute("INSERT OR REPLACE INTO assets VALUES (?, (SELECT COALESCE(qty,0) FROM assets WHERE item_name=?) + ?, ?)",
                       (item, item, amt, datetime.now().strftime("%Y-%m-%d %H:%M")))
            db.commit()
            st.success(f"Recorded {amt} {item}")
            st.rerun()
