import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime

# --- 1. CONFIG & DIRECTORIES ---
st.set_page_config(page_title="Mekgoro Inventory", layout="wide")
db = sqlite3.connect("mekgoro_v13.db", check_same_thread=False)

# Create a folder to save uploaded invoices/photos
if not os.path.exists("uploads"):
    os.makedirs("uploads")

def init_db():
    # Added 'file_path' to track the invoice/photo
    db.execute("""CREATE TABLE IF NOT EXISTS assets 
                  (item_name TEXT PRIMARY KEY, qty INTEGER, last_update TEXT)""")
    db.execute("""CREATE TABLE IF NOT EXISTS logs 
                  (type TEXT, item_name TEXT, qty INTEGER, ref_no TEXT, 
                   file_path TEXT, user TEXT, timestamp TEXT)""")
    db.commit()

init_db()

# --- 2. LOGIN ---
if "user" not in st.session_state:
    st.title("🛡️ Mekgoro Secure Login")
    name = st.selectbox("Who is logging in?", ["Ndule", "Tshepo (Driver)", "Biino", "Anthony", "Mike"])
    if st.button("Access Terminal"):
        st.session_state.user = name
        st.rerun()
    st.stop()

# --- 3. INTERFACE ---
st.title(f"🏗️ Mekgoro Terminal | User: {st.session_state.user}")
tab1, tab2, tab3, tab4 = st.tabs(["📊 Warehouse Ledger", "📥 Purchases & Uploads", "📤 Site Deliveries", "🕒 Activity Logs"])

with tab1:
    st.subheader("Current Warehouse Stock")
    search_main = st.text_input("🔍 Search Manual Items...")
    df_all = pd.read_sql("SELECT item_name as 'Item', qty as 'Stock' FROM assets ORDER BY item_name ASC", db)
    if search_main:
        df_all = df_all[df_all['Item'].str.contains(search_main, case=False, na=False)]
    st.dataframe(df_all, use_container_width=True)

with tab2:
    st.subheader("📥 Record Purchase (Manual + Invoice)")
    st.info("Fill this in when buying new stock. You can upload the PDF invoice or a Photo.")
    
    with st.form("purchase_form", clear_on_submit=True):
        p_name = st.text_input("Item Name (e.g., 50mm PVC Pipe)")
        p_qty = st.number_input("Quantity Received", min_value=1, step=1)
        p_ref = st.text_input("Supplier Name / Invoice #")
        
        # FILE UPLOAD (PDF or Image)
        uploaded_file = st.file_uploader("Upload Invoice (PDF) or Photo of Goods", type=['pdf', 'png', 'jpg', 'jpeg'])
        
        if st.form_submit_button("Save to Inventory"):
            if not p_name:
                st.error("Please enter the Item Name.")
            else:
                file_path = ""
                if uploaded_file is not None:
                    file_path = os.path.join("uploads", f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uploaded_file.name}")
                    with open(file_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                
                # Update Inventory
                db.execute("INSERT INTO assets (item_name, qty, last_update) VALUES (?, ?, ?) ON CONFLICT(item_name) DO UPDATE SET qty = qty + excluded.qty",
                           (p_name.strip(), int(p_qty), datetime.now().strftime("%Y-%m-%d %H:%M")))
                
                # Save Log with file path
                db.execute("INSERT INTO logs VALUES ('PURCHASE', ?, ?, ?, ?, ?, ?)", 
                           (p_name.strip(), int(p_qty), p_ref, file_path, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
                db.commit()
                st.success(f"Successfully recorded {p_qty} x {p_name}")
                st.rerun()

with tab3:
    st.subheader("📤 Record Delivery to Site")
    items_list = pd.read_sql("SELECT item_name, qty FROM assets", db)
    
    if items_list.empty:
        st.warning("No stock available to deliver yet. Record a Purchase first.")
    else:
        with st.form("delivery_form"):
            d_choice = st.selectbox("Select Item for Site", items_list['item_name'].tolist())
            d_bal = items_list[items_list['item_name'] == d_choice]['qty'].values[0]
            st.write(f"📦 **Currently Available: {int(d_bal)}**")
            
            d_qty = st.number_input("Quantity Leaving", min_value=1, step=1)
            d_site = st.text_input("Project Name / Site Address")
            
            if st.form_submit_button("Confirm Dispatch"):
                if d_qty > d_bal:
                    st.error("Not enough stock!")
                else:
                    db.execute("UPDATE assets SET qty = qty - ? WHERE item_name = ?", (int(d_qty), d_choice))
                    db.execute("INSERT INTO logs VALUES ('DELIVERY', ?, ?, ?, ?, ?, ?)", 
                               (d_choice, int(d_qty), d_site, "", st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
                    db.commit()
                    st.warning(f"Dispatched {d_qty} to {d_site}")
                    st.rerun()

with tab4:
    st.subheader("Activity History & Attachments")
    logs = pd.read_sql("SELECT timestamp, type, item_name, qty, ref_no as 'Ref/Site', file_path, user FROM logs ORDER BY timestamp DESC", db)
    
    # Display table with link to files
    for index, row in logs.iterrows():
        col1, col2, col3, col4, col5 = st.columns([2, 1, 2, 1, 1])
        with col1: st.write(row['timestamp'])
        with col2: st.write(row['type'])
        with col3: st.write(f"{row['qty']} x {row['item_name']}")
        with col4: st.write(row['Ref/Site'])
        with col5:
            if row['file_path']:
                # Provide a download button for the invoice/photo
                with open(row['file_path'], "rb") as f:
                    st.download_button("View Attachment", f, file_name=os.path.basename(row['file_path']))
            else:
                st.write("No File")
        st.divider()
