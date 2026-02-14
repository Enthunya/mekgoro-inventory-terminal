import streamlit as st
import pandas as pd
import sqlite3
import os
import pdfplumber
from datetime import datetime

# --- 1. CONFIG ---
st.set_page_config(page_title="Mekgoro Inventory", layout="wide")
db = sqlite3.connect("mekgoro_v16.db", check_same_thread=False)

if not os.path.exists("uploads"):
    os.makedirs("uploads")

def init_db():
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty INTEGER)")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty INTEGER, ref_no TEXT, file_path TEXT, user TEXT, timestamp TEXT)")
    db.commit()

init_db()

# --- 2. OMNISURGE SCANNER ENGINE ---
def scan_omnisurge_pdf(file):
    items_found = []
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                for row in table:
                    # Column 1: Description | Column 4: Quantity (Based on Omnisurge Layout)
                    if row[1] and "Description" not in row[1] and row[4]:
                        try:
                            desc = row[1].replace('\n', ' ').strip()
                            # Convert 1.00 to 1
                            qty = int(float(row[4]))
                            items_found.append({"name": desc, "qty": qty})
                        except:
                            continue
    return items_found

# --- 3. LOGIN ---
if "user" not in st.session_state:
    st.title("🛡️ Mekgoro Secure Login")
    name = st.selectbox("Staff Member", ["Ndule", "Tshepo (Driver)", "Biino", "Anthony", "Mike"])
    if st.button("Access Terminal"):
        st.session_state.user = name
        st.rerun()
    st.stop()

# --- 4. INTERFACE ---
st.title(f"🏗️ Mekgoro Terminal | User: {st.session_state.user}")
tab1, tab2, tab3 = st.tabs(["📊 Warehouse Ledger", "📥 Purchases & Auto-Scan", "📤 Site Deliveries"])

with tab1:
    st.subheader("Current Warehouse Stock")
    data = pd.read_sql("SELECT item_name as 'Item', qty as 'Stock' FROM assets ORDER BY item_name ASC", db)
    st.dataframe(data, use_container_width=True, height=400)

with tab2:
    st.subheader("📥 Receive New Stock")
    mode = st.radio("Choose Input Method:", ["Auto-Scan Omnisurge PDF", "Manual Entry"])
    
    if mode == "Auto-Scan Omnisurge PDF":
        uploaded_file = st.file_uploader("Upload PDF Invoice", type=['pdf'])
        if uploaded_file:
            extracted = scan_omnisurge_pdf(uploaded_file)
            if extracted:
                st.write("### Items Detected:")
                for item in extracted:
                    st.success(f"📦 {item['name']} | Quantity: {item['qty']}")
                
                ref_no = st.text_input("Enter Document No (e.g. ION127436)")
                if st.button("Confirm & Update Stock"):
                    f_path = os.path.join("uploads", f"{datetime.now().strftime('%Y%m%d')}_{uploaded_file.name}")
                    with open(f_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    
                    for item in extracted:
                        db.execute("INSERT INTO assets (item_name, qty) VALUES (?, ?) ON CONFLICT(item_name) DO UPDATE SET qty = qty + excluded.qty", (item['name'], item['qty']))
                        db.execute("INSERT INTO logs VALUES ('PURCHASE', ?, ?, ?, ?, ?, ?)", (item['name'], item['qty'], ref_no, f_path, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
                    db.commit()
                    st.success("Ledger updated!")
                    st.rerun()
            else:
                st.error("Scanner could not read items. Use Manual Entry instead.")

    else:
        with st.form("manual_form"):
            m_name = st.text_input("Item Name")
            m_qty = st.number_input("Quantity", min_value=1, step=1)
            m_ref = st.text_input("Invoice / Supplier Ref")
            if st.form_submit_button("Save Manual Entry"):
                db.execute("INSERT INTO assets (item_name, qty) VALUES (?, ?) ON CONFLICT(item_name) DO UPDATE SET qty = qty + excluded.qty", (m_name, int(m_qty)))
                db.execute("INSERT INTO logs VALUES ('PURCHASE', ?, ?, ?, ?, ?, ?)", (m_name, int(m_qty), m_ref, "", st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
                db.commit()
                st.rerun()

with tab3:
    st.subheader("📤 Record Site Delivery")
    items_list = pd.read_sql("SELECT item_name, qty FROM assets", db)
    if not items_list.empty:
        with st.form("delivery_form"):
            choice = st.selectbox("Select Item", items_list['item_name'].tolist())
            d_bal = items_list[items_list['item_name'] == choice]['qty'].values[0]
            st.info(f"Available in Warehouse: {int(d_bal)}")
            out_qty = st.number_input("Quantity for Dispatch", min_value=1, step=1)
            site = st.text_input("Project / Site Name")
            if st.form_submit_button("Confirm Delivery"):
                if out_qty > d_bal:
                    st.error("Insufficient Stock!")
                else:
                    db.execute("UPDATE assets SET qty = qty - ? WHERE item_name = ?", (int(out_qty), choice))
                    db.execute("INSERT INTO logs VALUES ('DELIVERY', ?, ?, ?, ?, ?, ?)", (choice, int(out_qty), site, "", st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
                    db.commit()
                    st.rerun()

