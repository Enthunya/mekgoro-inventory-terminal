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

# --- 2. DATABASE INITIALIZATION ---
db = sqlite3.connect("mekgoro_database.db", check_same_thread=False)

def init_db():
    # Create tables if they don't exist
    db.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            item_name TEXT PRIMARY KEY, 
            qty_on_hand INTEGER, 
            last_update TEXT
        )
    """)
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
    # Add a starting row if empty to prevent 'DatabaseError' on select
    check = db.execute("SELECT count(*) FROM assets").fetchone()[0]
    if check == 0:
        db.execute("INSERT INTO assets VALUES ('Example: Cement 50kg', 0, 'Initial Setup')")
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
    
    # NOTE: You can add 'parents': ['YOUR_FOLDER_ID'] here if you want a specific folder
    file_metadata = {'name': file_name}
    media = MediaFileUpload(temp_path, resumable=True)
    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
    
    os.remove(temp_path) 
    return file.get('webViewLink')

# --- 4. APP INTERFACE ---
st.title("🏗️ Mekgoro Smart Inventory System")

tab1, tab2, tab3 = st.tabs(["📥 Add Stock (Inbound)", "📤 Process P.O. (Outbound)", "📋 Warehouse Ledger"])

with tab1:
    st.subheader("Add Stock to Warehouse")
    with st.form("inbound_form"):
        supplier = st.text_input("Supplier Name")
        item = st.text_input("Item Name (e.g., Cement 50kg)")
        qty = st.number_input("Quantity Received", min_value=1)
        receipt = st.file_uploader("Upload Receipt/Invoice", type=['pdf', 'jpg', 'png'])
        
        if st.form_submit_button("Confirm Stock Entry"):
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            link = upload_to_drive(receipt, receipt.name) if receipt else "No Document"
            
            # Logic: Update existing item qty OR insert new
            db.execute("""
                INSERT INTO assets (item_name, qty_on_hand, last_update) 
                VALUES (?,?,?) 
                ON CONFLICT(item_name) DO UPDATE SET 
                qty_on_hand = qty_on_hand + excluded.qty_on_hand, 
                last_update = excluded.last_update
            """, (item, qty, now))
            
            db.execute("INSERT INTO logs VALUES (?,?,?,?,?,?,?,?)", 
                       ("INCOMING", item, qty, link, "Admin", now, "Verified", supplier))
            db.commit()
            st.success(f"✅ Successfully added {qty} {item}. Record stored.")

with tab2:
    st.subheader("Process & Check Client P.O.")
    # Pull current items for a dropdown
    item_list = [row[0] for row in db.execute("SELECT item_name FROM assets").fetchall()]
    
    with st.form("outbound_form"):
        po_item = st.selectbox("Select Item in Stock", item_list)
        po_qty = st.number_input("Quantity Requested on P.O.", min_value=1)
        
        if st.form_submit_button("Check Availability"):
            res = db.execute("SELECT qty_on_hand FROM assets WHERE item_name = ?", (po_item,)).fetchone()
            current_stock = res[0] if res else 0
            
            if current_stock >= po_qty:
                st.success(f"✅ STOCK AVAILABLE: You have {current_stock} units. You can safely process this P.O.")
                if st.checkbox("Ship now and subtract from inventory?"):
                    new_qty = current_stock - po_qty
                    now = datetime.now().strftime("%Y-%m-%d %H:%M")
                    db.execute("UPDATE assets SET qty_on_hand = ?, last_update = ? WHERE item_name = ?", (new_qty, now, po_item))
                    db.commit()
                    st.info("Stock updated and logged.")
            else:
                st.error(f"🚨 SHORTAGE: You only have {current_stock} units. You need {po_qty - current_stock} more to fulfill this order.")

with tab3:
    st.subheader("Current Warehouse Status")
    # Using the exact aliases the UI expects to prevent DatabaseErrors
    query = "SELECT item_name AS 'Item Name', qty_on_hand AS 'In Stock', last_update AS 'Last Activity' FROM assets"
    ledger_df = pd.read_sql(query, db)
    st.dataframe(ledger_df, use_container_width=True)

