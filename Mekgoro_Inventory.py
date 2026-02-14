import streamlit as st
import pandas as pd
import sqlite3
import os
import pdfplumber  # You must add this to your requirements.txt
from datetime import datetime

# --- 1. CONFIG ---
st.set_page_config(page_title="Mekgoro Inventory", layout="wide")
db = sqlite3.connect("mekgoro_v15.db", check_same_thread=False)

if not os.path.exists("uploads"):
    os.makedirs("uploads")

def init_db():
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty INTEGER)")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty INTEGER, ref_no TEXT, file_path TEXT, user TEXT, timestamp TEXT)")
    db.commit()

init_db()

# --- 2. THE SCANNER ENGINE ---
def scan_omnisurge_pdf(file):
    items_found = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                # Look for the row containing 'Description' and 'Quantity'
                for row in table:
                    # Filter out header rows or empty rows
                    if row[1] and "Description" not in row[1] and row[4]:
                        try:
                            desc = row[1].replace('\n', ' ').strip()
                            qty = int(float(row[4]))
                            items_found.append({"name": desc, "qty": qty})
                        except:
                            continue
    return items_found

# --- 3. LOGIN ---
if "user" not in st.session_state:
    st.title("🛡️ Mekgoro Secure Login")
    name = st.selectbox("Staff Member", ["Ndule", "Tshepo (Driver)", "Biino"])
    if st.button("Access Terminal"):
        st.session_state.user = name
        st.rerun()
    st.stop()

# --- 4. INTERFACE ---
st.title(f"🏗️ Mekgoro Terminal | User: {st.session_state.user}")
tab1, tab2, tab3 = st.tabs(["📊 Warehouse Ledger", "📥 Upload & Auto-Scan", "📤 Site Deliveries"])

with tab1:
    st.subheader("Current Warehouse Stock")
    data = pd.read_sql("SELECT item_name as 'Item', qty as 'Stock' FROM assets ORDER BY item_name ASC", db)
    st.dataframe(data, use_container_width=True)

with tab2:
    st.subheader("📥 Auto-Scan Supplier Invoice")
    st.write("Upload the Omnisurge PDF to automatically update stock.")
    
    # PDF Upload
    uploaded_file = st.file_uploader("Upload PDF Invoice", type=['pdf'])
    
    if uploaded_file is not None:
        # Extract data using our scanner
        extracted_items = scan_omnisurge_pdf(uploaded_file)
        
        if not extracted_items:
            st.error("Could not find items in this PDF. Please enter manually.")
        else:
            st.write("### Items Detected:")
            for item in extracted_items:
                st.write(f"✅ {item['name']} - **Qty: {item['qty']}**")
            
            ref_no = st.text_input("Enter Document Number (e.g. ION127436)")
            
            if st.button("Confirm & Update Ledger"):
                # Save the file first
                f_path = os.path.join("uploads", f"{datetime.now().strftime('%Y%m%d')}_{uploaded_file.name}")
                with open(f_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                # Process each item found in PDF
                for item in extracted_items:
                    db.execute("INSERT INTO assets (item_name, qty) VALUES (?, ?) ON CONFLICT(item_name) DO UPDATE SET qty = qty + excluded.qty",
                               (item['name'], item['qty']))
                    db.execute("INSERT INTO logs VALUES ('PURCHASE', ?, ?, ?, ?, ?, ?)", 
                               (item['name'], item['qty'], ref_no, f_path, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
                
                db.commit()
                st.success("Ledger Updated Successfully!")
                st.rerun()

with tab3:
    st.subheader("📤 Record Site Delivery")
    items_list = pd.read_sql("SELECT item_name, qty FROM assets", db)
    if not items_list.empty:
        with st.form("delivery_form"):
            choice = st.selectbox("Item", items_list['item_name'].tolist())
            d_qty = st.number_input("Quantity Out", min_value=1, step=1)
            site = st.text_input("Project Site")
            if st.form_submit_button("Confirm Dispatch"):
                db.execute("UPDATE assets SET qty = qty - ? WHERE item_name = ?", (int(d_qty), choice))
                db.execute("INSERT INTO logs VALUES ('DELIVERY', ?, ?, ?, ?, ?, ?)", 
                           (choice, int(d_qty), site, "", st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
                db.commit()
                st.rerun()
