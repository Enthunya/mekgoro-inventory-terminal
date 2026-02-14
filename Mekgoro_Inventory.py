import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime

# --- 1. CONFIG & DATABASE ---
st.set_page_config(page_title="Mekgoro Inventory", layout="wide")
db = sqlite3.connect("mekgoro_v12.db", check_same_thread=False)

def init_db():
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty INTEGER, last_update TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty INTEGER, ref_no TEXT, user TEXT, timestamp TEXT)")
    db.commit()

    # AUTO-LOAD FROM SAGE FILE (If empty)
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM assets")
    if cursor.fetchone()[0] == 0:
        for f in ["ItemListingReport.csv", "ItemListingReport.xlsx"]:
            if os.path.exists(f):
                try:
                    df = pd.read_excel(f) if f.endswith('.xlsx') else pd.read_csv(f, skiprows=1)
                    if 'Description' in df.columns:
                        for _, row in df.iterrows():
                            name = str(row['Description']).strip()
                            if name and name != 'nan':
                                q_val = row.get('Qty on Hand', 0)
                                initial_qty = int(abs(float(q_val))) if pd.notnull(q_val) else 0
                                db.execute("INSERT OR IGNORE INTO assets VALUES (?, ?, ?)",
                                           (name, initial_qty, datetime.now().strftime("%Y-%m-%d %H:%M")))
                        db.commit()
                        break
                except: continue

init_db()

# --- 2. LOGIN ---
if "user" not in st.session_state:
    st.title("🛡️ Mekgoro Secure Login")
    name = st.selectbox("Who is logging in?", ["Ndule", "Tshepo (Driver)", "Biino", "Anthony", "Mike"])
    if st.button("Access Terminal"):
        st.session_state.user = name
        st.rerun()
    st.stop()

# --- 3. MAIN INTERFACE ---
st.title(f"🏗️ Mekgoro Terminal | User: {st.session_state.user}")
tab1, tab2, tab3, tab4 = st.tabs(["📊 Total Available", "📥 Purchases", "📤 Deliveries", "🕒 History"])

def get_all_items():
    return pd.read_sql("SELECT item_name, qty FROM assets ORDER BY item_name ASC", db)

with tab1:
    st.subheader("Warehouse Inventory Search")
    search_main = st.text_input("🔍 Search for any item...", placeholder="Type to filter list")
    df_all = get_all_items()
    if search_main:
        df_all = df_all[df_all['item_name'].str.contains(search_main, case=False, na=False)]
    st.dataframe(df_all.rename(columns={'item_name': 'Description', 'qty': 'Stock Level'}), use_container_width=True, height=500)

with tab2:
    st.subheader("📥 Record New Purchases")
    
    # --- PART 1: SEARCH EXISTING SAGE ITEMS ---
    st.markdown("### Option 1: Add to Existing Sage Item")
    search_in = st.text_input("🔍 Type to find item bought...", key="search_in")
    df_in = get_all_items()
    filtered_in = [x for x in df_in['item_name'].tolist() if search_in.lower() in x.lower()] if search_in else df_in['item_name'].tolist()
    
    with st.form("purchase_form"):
        choice = st.selectbox("Select item from list:", filtered_in)
        qty_in = st.number_input("Quantity Received", min_value=1, step=1)
        ref = st.text_input("Supplier Invoice #", key="ref_in")
        if st.form_submit_button("Add to Stock"):
            db.execute("UPDATE assets SET qty = qty + ? WHERE item_name = ?", (int(qty_in), choice))
            db.execute("INSERT INTO logs VALUES ('PURCHASE', ?, ?, ?, ?, ?)", (choice, int(qty_in), ref, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
            db.commit()
            st.success(f"Added {int(qty_in)} units to {choice}")
            st.rerun()

    st.markdown("---")
    
    # --- PART 2: MANUAL ENTRY FOR NEW ITEMS ---
    st.markdown("### Option 2: Add BRAND NEW Item (Not in Sage)")
    with st.form("manual_add_form"):
        new_name = st.text_input("New Item Description (Be precise!)")
        new_qty = st.number_input("Initial Quantity", min_value=1, step=1)
        new_ref = st.text_input("Delivery Note / Invoice #", key="ref_manual")
        if st.form_submit_button("Create & Save New Item"):
            if new_name.strip() == "":
                st.error("Please enter a name for the new item.")
            else:
                db.execute("INSERT OR IGNORE INTO assets VALUES (?, ?, ?)", (new_name.strip(), int(new_qty), datetime.now().strftime("%Y-%m-%d %H:%M")))
                db.execute("INSERT INTO logs VALUES ('NEW_ITEM', ?, ?, ?, ?, ?)", (new_name.strip(), int(new_qty), new_ref, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
                db.commit()
                st.success(f"New item '{new_name}' created and added to stock!")
                st.rerun()

with tab3:
    st.subheader("📤 Record Site Deliveries")
    search_out = st.text_input("🔍 Type to find item for delivery...", key="search_out")
    df_out = get_all_items()
    filtered_out = [x for x in df_out['item_name'].tolist() if search_out.lower() in x.lower()] if search_out else df_out['item_name'].tolist()
    
    if not filtered_out:
        st.warning("No matching items found.")
    else:
        with st.form("delivery_form"):
            choice = st.selectbox("Select item for dispatch:", filtered_out)
            current_bal = df_out[df_out['item_name'] == choice]['qty'].values[0]
            st.write(f"📦 **Currently in Warehouse: {int(current_bal)}**")
            qty_out = st.number_input("Quantity to Dispatch", min_value=1, step=1)
            project = st.text_input("Project / Site Name")
            if st.form_submit_button("Confirm Dispatch"):
                if int(qty_out) > current_bal:
                    st.error(f"Cannot dispatch {int(qty_out)}. Only {int(current_bal)} available.")
                else:
                    db.execute("UPDATE assets SET qty = qty - ? WHERE item_name = ?", (int(qty_out), choice))
                    db.execute("INSERT INTO logs VALUES ('DELIVERY', ?, ?, ?, ?, ?)", (choice, int(qty_out), project, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
                    db.commit()
                    st.warning("Dispatched to site.")
                    st.rerun()

with tab4:
    st.subheader("Recent Activity History")
    logs = pd.read_sql("SELECT timestamp, type as 'Action', item_name, CAST(qty AS INT) as 'Quantity', ref_no as 'Ref/Project', user FROM logs ORDER BY timestamp DESC", db)
    st.dataframe(logs, use_container_width=True)
