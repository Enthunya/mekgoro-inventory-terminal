import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import re

# --- 1. CONFIG ---
st.set_page_config(page_title="Mekgoro Smart Inventory", page_icon="🏗️", layout="wide")

# --- 2. DATABASE ---
db = sqlite3.connect("mekgoro_database.db", check_same_thread=False)

def init_db():
    # Assets tracks physical stock
    db.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            item_name TEXT PRIMARY KEY,
            qty_on_hand INTEGER,
            last_update TEXT
        )
    """)
    # Logs tracks every single movement for Mike & Anthony to audit
    db.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            type TEXT,
            item_name TEXT,
            qty INTEGER,
            ref_doc TEXT,
            user TEXT,
            timestamp TEXT,
            status TEXT,
            supplier TEXT
        )
    """)
    db.commit()

init_db()

# --- 3. GOOGLE DRIVE SETUP (Using Secrets) ---
SCOPES = ['https://www.googleapis.com/auth/drive.file']

if "gcp_service_account" in st.secrets:
    info = dict(st.secrets["gcp_service_account"])
    credentials = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    drive_service = build('drive', 'v3', credentials=credentials)
else:
    st.error("⚠️ Google Secrets not found in Streamlit Settings!")
    st.stop()

def upload_to_drive(file_obj, file_name):
    temp_path = f"temp_{file_name}"
    with open(temp_path, "wb") as f: 
        f.write(file_obj.getbuffer())
    file_metadata = {'name': file_name}
    media = MediaFileUpload(temp_path, resumable=True)
    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
    os.remove(temp_path)
    return file.get('webViewLink')

# --- 4. SECURITY: SANITIZE SUPPLIER DATA ---
def sanitize_text(text):
    # Removes emails and phone numbers to protect client privacy
    text = re.sub(r'\S+@\S+', '[REDACTED]', text)
    text = re.sub(r'\b\d{7,15}\b', '[REDACTED]', text)
    return text

# --- 5. LOGIN SYSTEM ---
if "user_name" not in st.session_state:
    st.title("🛡️ Mekgoro Secure Login")
    user = st.selectbox("Who is accessing the terminal?", ["Manager", "Biino", "Anthony", "Mike", "Gunman"])
    if st.button("Enter Terminal"):
        st.session_state.user_name = user
        st.rerun()
    st.stop()

# --- 6. MAIN TERMINAL INTERFACE ---
st.title(f"🏗️ Mekgoro Smart Inventory (User: {st.session_state.user_name})")
tab1, tab2, tab3, tab4 = st.tabs(["📥 Add Stock", "📤 Process P.O.", "📋 Warehouse Ledger", "🏢 Supplier Ledger"])

with tab1:
    st.subheader("Add Stock (Receipt Upload)")
    with st.form("inbound"):
        supplier = st.text_input("Supplier Name")
        item = st.text_input("Item Name (e.g., Cement 50kg)")
        qty = st.number_input("Quantity Received", min_value=1)
        receipt = st.file_uploader("Upload Receipt", type=['pdf','jpg','png'])
        if st.form_submit_button("Confirm Entry"):
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            link = upload_to_drive(receipt, receipt.name) if receipt else "No Doc"
            db.execute("INSERT INTO assets VALUES (?,?,?) ON CONFLICT(item_name) DO UPDATE SET qty_on_hand=qty_on_hand+?, last_update=?", (item, qty, now, qty, now))
            db.execute("INSERT INTO logs VALUES (?,?,?,?,?,?,?,?)", ("INCOMING", item, qty, link, st.session_state.user_name, now, "Verified", supplier))
            db.commit()
            st.success(f"Stock Updated: {qty} {item} added.")

with tab2:
    st.subheader("Check & Process Client P.O.")
    items = [r[0] for r in db.execute("SELECT item_name FROM assets").fetchall()]
    with st.form("outbound"):
        po_item = st.selectbox("Select Item", items) if items else st.info("Add stock first!")
        po_qty = st.number_input("Quantity on P.O.", min_value=1)
        if st.form_submit_button("Verify Stock"):
            res = db.execute("SELECT qty_on_hand FROM assets WHERE item_name=?", (po_item,)).fetchone()
            current = res[0] if res else 0
            if current >= po_qty:
                st.success(f"✅ AVAILABLE: {current} in stock.")
                # Logic to subtract stock would go here
            else:
                st.error(f"🚨 SHORTAGE: Need {po_qty - current} more.")

with tab3:
    st.subheader("Live Warehouse Status")
    df = pd.read_sql("SELECT item_name AS 'Item', qty_on_hand AS 'In Stock', last_update AS 'Last Activity' FROM assets", db)
    st.dataframe(df, use_container_width=True)

with tab4:
    st.subheader("Supplier Activity & Re-order Insights")
    logs = pd.read_sql("SELECT supplier, item_name, qty, timestamp FROM logs WHERE type='INCOMING'", db)
    st.write("Recent Supplier Deliveries:")
    st.table(logs)
