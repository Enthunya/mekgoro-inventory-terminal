import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Mekgoro Terminal", page_icon="🏗️", layout="wide")

# --- 2. DATABASE ---
db = sqlite3.connect("mekgoro_database.db", check_same_thread=False)

def init_db():
    # Assets tracks physical stock; Logs tracks every movement
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty_on_hand INTEGER, last_update TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty INTEGER, ref_doc TEXT, user TEXT, timestamp TEXT, status TEXT, supplier TEXT)")
    db.commit()

init_db()

# --- 3. GOOGLE DRIVE AUTH (Using Secrets) ---
SCOPES = ['https://www.googleapis.com/auth/drive.file']

if "gcp_service_account" in st.secrets:
    info = dict(st.secrets["gcp_service_account"])
    credentials = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    drive_service = build('drive', 'v3', credentials=credentials)
else:
    st.error("⚠️ Google Secrets not found in Streamlit Settings!")
    st.stop()

def upload_to_drive(file_obj, file_name):
    """Saves file temporarily then uploads to Google Drive"""
    temp_path = f"temp_{file_name}"
    with open(temp_path, "wb") as f:
        f.write(file_obj.getbuffer())
    
    file_metadata = {'name': file_name}
    media = MediaFileUpload(temp_path, resumable=True)
    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
    
    os.remove(temp_path) # Clean up
    return file.get('webViewLink')

# --- 4. THE SMART WORKFLOW ---
st.title("🏗️ Mekgoro Smart Inventory System")

tab1, tab2, tab3 = st.tabs(["📥 Add Stock (Receipts)", "📤 Process P.O. (Client Orders)", "📋 Warehouse Ledger"])

with tab1:
    st.subheader("Add Stock to Warehouse")
    with st.form("inbound"):
        supplier = st.text_input("Supplier Name")
        item = st.text_input("Item Name (e.g., Cement 50kg)")
        qty = st.number_input("Quantity Received", min_value=1)
        receipt = st.file_uploader("Upload Receipt/Invoice", type=['pdf', 'jpg', 'png'])
        
        if st.form_submit_button("Confirm Stock Entry"):
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            link = upload_to_drive(receipt, receipt.name) if receipt else "Manual"
            
            db.execute("INSERT INTO assets (item_name, qty_on_hand, last_update) VALUES (?,?,?) ON CONFLICT(item_name) DO UPDATE SET qty_on_hand = qty_on_hand + ?, last_update = ?", (item, qty, now, qty, now))
            db.execute("INSERT INTO logs VALUES (?,?,?,?,?,?,?,?)", ("INCOMING", item, qty, link, "User", now, "Added", supplier))
            db.commit()
            st.success(f"✅ Added {qty} {item} to stock. Document saved to Drive.")

with tab2:
    st.subheader("Process & Check Client P.O.")
    with st.form("outbound"):
        po_item = st.text_input("Item requested")
        po_qty = st.number_input("Quantity requested", min_value=1)
        po_file = st.file_uploader("Upload Client P.O.", type=['pdf'])
        
        if st.form_submit_button("Verify Stock Availability"):
            res = db.execute("SELECT qty_on_hand FROM assets WHERE item_name = ?", (po_item,)).fetchone()
            current = res[0] if res else 0
            
            if current >= po_qty:
                st.success(f"✅ AVAILABLE: You have {current} in stock. Ready to ship.")
                if st.checkbox("Confirm Shipment (Subtract Stock)"):
                    now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    db.execute("UPDATE assets SET qty_on_hand = qty_on_hand - ? WHERE item_name = ?", (po_qty, po_item))
                    db.commit()
                    st.info("Stock updated. Order processed.")
            else:
                shortage = po_qty - current
                st.error(f"🚨 INSUFFICIENT STOCK: You only have {current}. You need to buy {shortage} more {po_item}.")

with tab3:
    st.subheader("Warehouse Status")
    ledger = pd.read_sql("SELECT item_name as 'Item', qty_on_hand as 'In Stock', last_update as 'Last Activity' FROM assets", db)
    st.dataframe(ledger, use_container_width=True)
