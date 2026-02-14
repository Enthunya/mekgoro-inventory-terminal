import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- 1. CONFIG & REPAIR ---
st.set_page_config(page_title="Mekgoro Terminal", page_icon="🏗️", layout="wide")

db = sqlite3.connect("mekgoro_database.db", check_same_thread=False)

def init_db():
    # Force a fresh start to fix the 'OperationalError'
    db.execute("DROP TABLE IF EXISTS assets")
    db.execute("CREATE TABLE assets (item_name TEXT PRIMARY KEY, qty_on_hand INTEGER, last_update TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty INTEGER, ref_doc TEXT, user TEXT, timestamp TEXT, status TEXT, supplier TEXT)")
    db.commit()

# Run the repair logic once
if 'repair_done' not in st.session_state:
    init_db()
    st.session_state.repair_done = True

# --- 2. SECURE AUTH ---
if "gcp_service_account" in st.secrets:
    info = dict(st.secrets["gcp_service_account"])
    credentials = service_account.Credentials.from_service_account_info(info, scopes=['https://www.googleapis.com/auth/drive.file'])
    drive_service = build('drive', 'v3', credentials=credentials)
else:
    st.error("⚠️ Secrets not found! Please check your Streamlit Settings.")
    st.stop()

# --- 3. LOGIN & APP ---
if "user" not in st.session_state:
    st.title("🛡️ Mekgoro Secure Login")
    name = st.selectbox("Select User:", ["Manager", "Biino", "Anthony", "Mike"])
    if st.button("Enter"):
        st.session_state.user = name
        st.rerun()
    st.stop()

st.title(f"🏗️ Mekgoro Smart Inventory | User: {st.session_state.user}")
tab1, tab2, tab3 = st.tabs(["📥 Add Stock", "📤 Process P.O.", "📋 Warehouse Ledger"])

with tab1:
    st.subheader("Register Inbound Stock")
    with st.form("add"):
        item = st.text_input("Item Name")
        qty = st.number_input("Quantity", min_value=1)
        if st.form_submit_button("Confirm"):
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            db.execute("INSERT INTO assets VALUES (?,?,?) ON CONFLICT(item_name) DO UPDATE SET qty_on_hand=qty_on_hand+?", (item, qty, now, qty))
            db.commit()
            st.success(f"Added {qty} {item}")

with tab3:
    st.subheader("Current Stock")
    data = pd.read_sql("SELECT item_name as 'Item', qty_on_hand as 'In Stock' FROM assets", db)
    st.dataframe(data, use_container_width=True)

