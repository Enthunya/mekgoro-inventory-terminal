import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- 1. CONFIG & DB ---
st.set_page_config(page_title="Mekgoro Terminal", layout="wide")
db = sqlite3.connect("mekgoro_database.db", check_same_thread=False)

def init_db():
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty_on_hand INTEGER, last_update TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty INTEGER, ref_doc TEXT, user TEXT, timestamp TEXT)")
    db.commit()

init_db()

# --- 2. GOOGLE DRIVE AUTH (THE SIMPLE WAY) ---
SCOPES = ['https://www.googleapis.com/auth/drive.file']
JSON_FILE = "service_account.json"

if os.path.exists(JSON_FILE):
    try:
        credentials = service_account.Credentials.from_service_account_file(JSON_FILE, scopes=SCOPES)
        drive_service = build('drive', 'v3', credentials=credentials)
    except Exception as e:
        st.error(f"❌ Auth Error: {e}")
        st.stop()
else:
    st.error("⚠️ service_account.json not found in GitHub folder!")
    st.stop()

# --- 3. LOGIN & TABS ---
if "user" not in st.session_state:
    st.title("🛡️ Mekgoro Secure Login")
    name = st.selectbox("Who is logging in?", ["Manager", "Biino", "Anthony", "Mike", "Gunman"])
    if st.button("Enter Terminal"):
        st.session_state.user = name
        st.rerun()
    st.stop()

st.title(f"🏗️ Mekgoro Smart Inventory | User: {st.session_state.user}")
tab1, tab2, tab3 = st.tabs(["📥 Add Stock", "📤 Process P.O.", "📋 Warehouse Ledger"])

# (Rest of your tab logic goes here...)
