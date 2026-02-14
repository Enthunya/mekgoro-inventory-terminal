import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime

# --- 1. CONFIG & BRANDING ---
st.set_page_config(page_title="Mekgoro Inventory Terminal", layout="wide", page_icon="🏗️")
db = sqlite3.connect("mekgoro_learning.db", check_same_thread=False)

if not os.path.exists("uploads"):
    os.makedirs("uploads")

# --- CUSTOM LOGO FUNCTION ---
def display_branding():
    col1, col2 = st.columns([1, 4])
    # Place your logo.png in the GitHub folder
    if os.path.exists("logo.png"):
        col1.image("logo.png", width=150)
    else:
        # Professional text version if logo file is missing
        col1.markdown("### 🏗️ MEKGORO")
    
    col2.title("Inventory Management Terminal")
    col2.write(f"Logged in as: **{st.session_state.user}** | {datetime.now().strftime('%d %b %Y')}")
    st.divider()

def init_db():
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty INTEGER)")
    db.execute("CREATE TABLE IF NOT EXISTS supplier_memory (supplier TEXT, item_name TEXT, UNIQUE(supplier, item_name))")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty INTEGER, ref_no TEXT, file_path TEXT, user TEXT, timestamp TEXT, supplier TEXT)")
    db.commit()

init_db()

# --- 2. LOGIN ---
if "user" not in st.session_state:
    st.title("🛡️ Mekgoro Secure Access")
    if os.path.exists("logo.png"):
        st.image("logo.png", width=200)
    name = st.selectbox("Select Staff Member", ["Ndule", "Tshepo (Driver)", "Biino", "Anthony", "Mike"])
    if st.button("Access Terminal"):
        st.session_state.user = name
        st.rerun()
    st.stop()

# --- 3. INTERFACE ---
display_branding() # This puts your logo on top of every tab

tab1, tab2, tab3 = st.tabs(["📊 Warehouse Ledger", "📥 Purchases (Stock IN)", "📤 Deliveries (Stock OUT)"])

with tab1:
    st.subheader("Warehouse Inventory Status")
    search_main = st.text_input("🔍 Quick Search Stock...", placeholder="Type item name...")
    df_all = pd.read_sql("SELECT item_name as 'Item Description', qty as 'Total Available' FROM assets ORDER BY item_name ASC", db)
    if search_main:
        df_all = df_all[df_all['Item Description'].str.contains(search_main, case=False, na=False)]
    
    # Using a styled table for the ledger
    st.dataframe(df_all, use_container_width=True, height=400)

with tab2:
    st.subheader("📥 Receive New Stock")
    existing_suppliers = pd.read_sql("SELECT DISTINCT supplier FROM supplier_memory", db)['supplier'].tolist()
    
    col_s1, col_s2 = st.columns([1, 1])
    vendor_choice = col_s1.selectbox("Supplier", ["-- New Supplier --"] + sorted(existing_suppliers))
    vendor = col_s2.text_input("New Supplier Name") if vendor_choice == "-- New Supplier --" else vendor_choice

    if vendor:
        supplier_items = pd.read_sql("SELECT item_name FROM supplier_memory WHERE supplier = ?", db, params=(vendor,))['item_name'].tolist()
        
        with st.form("purchase_form", clear_on_submit=True):
            p_name = st.selectbox("Predictive Item Search", ["-- Select Item --"] + sorted(supplier_items))
            new_item_toggle = st.checkbox("New item for this supplier?")
            manual_name = st.text_input("Enter Description (from Invoice)") if new_item_toggle or not supplier_items else ""
            
            final_name = manual_name.strip() if (new_item_toggle or not supplier_items) else p_name
            
            c1, c2 = st.columns(2)
            p_qty = c1.number_input("Quantity Received", min_value=1, step=1)
            p_ref = c2.text_input("Invoice/Document #")
            
            up_file = st.file_uploader("Upload Invoice Photo/PDF", type=['pdf', 'png', 'jpg', 'jpeg'])
            
            if st.form_submit_button("Update Warehouse Stock"):
                if not final_name or final_name == "-- Select Item --":
                    st.error("Please provide an Item Name.")
                else:
                    f_path = ""
                    if up_file:
                        f_path = os.path.join("uploads", f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{up_file.name}")
                        with open(f_path, "wb") as f:
                            f.write(up_file.getbuffer())
                    
                    db.execute("INSERT INTO assets (item_name, qty) VALUES (?, ?) ON CONFLICT(item_name) DO UPDATE SET qty = qty + excluded.qty", (final_name, int(p_qty)))
                    db.execute("INSERT OR IGNORE INTO supplier_memory VALUES (?, ?)", (vendor, final_name))
                    db.execute("INSERT INTO logs VALUES ('PURCHASE', ?, ?, ?, ?, ?, ?, ?)", (final_name, int(p_qty), p_ref, f_path, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M"), vendor))
                    db.commit()
                    st.success(f"Stock Updated: {final_name}")
                    st.rerun()

with tab3:
    st.subheader("📤 Record Site Delivery")
    items_list = pd.read_sql("SELECT item_name, qty FROM assets WHERE qty > 0", db)
    
    if items_list.empty:
        st.warning("Warehouse is empty.")
    else:
        with st.form("delivery_form"):
            d_choice = st.selectbox("Item Description", items_list['item_name'].tolist())
            d_bal = items_list[items_list['item_name'] == d_choice]['qty'].values[0]
            st.info(f"Available: {int(d_bal)}")
            
            d_qty = st.number_input("Quantity Out", min_value=1, step=1)
            d_site = st.text_input("Project / Site Name")
            
            if st.form_submit_button("Confirm Dispatch"):
                if d_qty > d_bal:
                    st.error("Insufficient Stock!")
                else:
                    db.execute("UPDATE assets SET qty = qty - ? WHERE item_name = ?", (int(d_qty), d_choice))
                    db.execute("INSERT INTO logs VALUES ('DELIVERY', ?, ?, ?, ?, ?, ?, 'INTERNAL')", (d_choice, int(d_qty), d_site, "", st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M"), "INTERNAL"))
                    db.commit()
                    st.rerun()
