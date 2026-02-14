import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime

# --- 1. CONFIG & DATABASE ---
st.set_page_config(page_title="Mekgoro Inventory", layout="wide")
# Using v11 to reset the search logic
db = sqlite3.connect("mekgoro_v11.db", check_same_thread=False)

def init_db():
    db.execute("CREATE TABLE IF NOT EXISTS assets (item_name TEXT PRIMARY KEY, qty INTEGER, last_update TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS logs (type TEXT, item_name TEXT, qty INTEGER, ref_no TEXT, user TEXT, timestamp TEXT)")
    db.commit()

    # AUTO-LOAD FROM SAGE FILE
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM assets")
    if cursor.fetchone()[0] == 0:
        for f in ["ItemListingReport.csv", "ItemListingReport.xlsx"]:
            if os.path.exists(f):
                try:
                    # Sage CSVs usually have a 'sep=,' header, so we skip row 0
                    df = pd.read_excel(f) if f.endswith('.xlsx') else pd.read_csv(f, skiprows=1)
                    
                    # Exact column matching for your Sage file
                    if 'Description' in df.columns:
                        for _, row in df.iterrows():
                            name = str(row['Description']).strip()
                            # Handle empty or NaN descriptions
                            if name and name != 'nan':
                                # Convert 'Qty on Hand' safely to integer
                                q_val = row.get('Qty on Hand', 0)
                                initial_qty = int(abs(float(q_val))) if pd.notnull(q_val) else 0
                                
                                db.execute("INSERT OR IGNORE INTO assets VALUES (?, ?, ?)",
                                           (name, initial_qty, datetime.now().strftime("%Y-%m-%d %H:%M")))
                        db.commit()
                        break
                except Exception as e:
                    continue

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

# Helper function to get the current list
def get_all_items():
    return pd.read_sql("SELECT item_name, qty FROM assets ORDER BY item_name ASC", db)

with tab1:
    st.subheader("Warehouse Inventory Search")
    search_main = st.text_input("🔍 Search for any item in the warehouse...", placeholder="Type here (e.g. Glove, Cable, Glue)")
    df_all = get_all_items()
    
    if search_main:
        df_all = df_all[df_all['item_name'].str.contains(search_main, case=False, na=False)]
    
    st.dataframe(df_all.rename(columns={'item_name': 'Description', 'qty': 'Stock Level'}), use_container_width=True, height=500)

with tab2:
    st.subheader("📥 Record New Purchases")
    search_in = st.text_input("🔍 Type to find item bought...", key="search_in")
    df_in = get_all_items()
    
    # Filter the list based on search
    filtered_in = df_in['item_name'].tolist()
    if search_in:
        filtered_in = [x for x in filtered_in if search_in.lower() in x.lower()]
    
    if not filtered_in:
        st.warning("No matching items found. Please check your spelling.")
    else:
        with st.form("purchase_form"):
            choice = st.selectbox("Select exact item from results:", filtered_in)
            qty_in = st.number_input("Quantity Received (Whole Number)", min_value=1, step=1, value=1)
            ref = st.text_input("Supplier Invoice / Ref #")
            if st.form_submit_button("Add to Stock"):
                db.execute("UPDATE assets SET qty = qty + ? WHERE item_name = ?", (int(qty_in), choice))
                db.execute("INSERT INTO logs VALUES ('PURCHASE', ?, ?, ?, ?, ?)", 
                           (choice, int(qty_in), ref, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
                db.commit()
                st.success(f"Added {int(qty_in)} to stock.")
                st.rerun()

with tab3:
    st.subheader("📤 Record Site Deliveries")
    search_out = st.text_input("🔍 Type to find item for delivery...", key="search_out")
    df_out = get_all_items()
    
    filtered_out = df_out['item_name'].tolist()
    if search_out:
        filtered_out = [x for x in filtered_out if search_out.lower() in x.lower()]
    
    if not filtered_out:
        st.warning("No matching items found.")
    else:
        with st.form("delivery_form"):
            choice = st.selectbox("Select exact item:", filtered_out)
            
            # Safe balance lookup
            current_bal = df_out[df_out['item_name'] == choice]['qty'].values[0]
            st.write(f"📦 **Currently in Warehouse: {int(current_bal)}**")
            
            qty_out = st.number_input("Quantity to Dispatch (Whole Number)", min_value=1, step=1, value=1)
            project = st.text_input("Project / Site Name")
            
            if st.form_submit_button("Confirm Dispatch"):
                if int(qty_out) > current_bal:
                    st.error(f"Cannot dispatch {int(qty_out)}. Only {int(current_bal)} available.")
                else:
                    db.execute("UPDATE assets SET qty = qty - ? WHERE item_name = ?", (int(qty_out), choice))
                    db.execute("INSERT INTO logs VALUES ('DELIVERY', ?, ?, ?, ?, ?)", 
                               (choice, int(qty_out), project, st.session_state.user, datetime.now().strftime("%Y-%m-%d %H:%M")))
                    db.commit()
                    st.warning("Dispatched to site.")
                    st.rerun()

with tab4:
    st.subheader("Recent Activity History")
    logs = pd.read_sql("SELECT timestamp, type as 'Action', item_name, CAST(qty AS INT) as 'Quantity', ref_no as 'Project/Ref', user FROM logs ORDER BY timestamp DESC", db)
    st.dataframe(logs, use_container_width=True)
