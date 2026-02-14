import streamlit as st
import sqlite3
import pandas as pd
import urllib.parse
from datetime import datetime
import os

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Mekgoro Terminal", page_icon="🏗️", layout="wide")

# Custom CSS for Mekgoro Branding (matching your logo's green)
st.markdown("""
<style>
    .stButton>button {background-color: #2D5A27; color:white; border-radius:8px; width:100%;}
    [data-testid="stSidebar"] {background-color: #f1f3f1;}
    .stTabs [data-baseweb="tab-list"] {gap: 20px;}
    .stMetric {background-color: #ffffff; padding: 15px; border-radius: 10px; border: 1px solid #e6e9ef;}
</style>
""", unsafe_allow_html=True)

# --- 2. DATABASE & TEAM DATA ---
db = sqlite3.connect("mekgoro_database.db", check_same_thread=False)

def init_db():
    db.execute("CREATE TABLE IF NOT EXISTS assets (asset_id TEXT PRIMARY KEY, description TEXT, qty INTEGER, last_updated TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS history (item_desc TEXT, qty_added INTEGER, date TEXT, supplier TEXT, unit_price REAL, updated_by TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS client_orders (client_name TEXT, item_desc TEXT, qty_ordered INTEGER, qty_remaining INTEGER, po_date TEXT, status TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS audit_logs (username TEXT, action TEXT, timestamp TEXT)")
    db.commit()

init_db()

TEAM_CONFIG = {"Manager (You)": "1111", "Biino (Accountant)": "2222", "Gunman (Driver/Inv)": "3333", "Anthony (Director)": "4444", "Mike (Director)": "5555"}
TEAM_PHONES = {"You": "27719620352", "Biino": "27690403000", "Gunman": "27695311451", "Anthony": "27828350250", "Mike": "27722978978"}

# --- 3. LOGIN SYSTEM ---
if "user_name" not in st.session_state:
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
        st.subheader("🛡️ Mekgoro Smart Inventory")
        user_sel = st.selectbox("Select User", list(TEAM_CONFIG.keys()))
        pin_in = st.text_input("Enter PIN", type="password")
        if st.button("Unlock Terminal"):
            if pin_in == TEAM_CONFIG[user_sel]:
                st.session_state.user_name, st.session_state.role = user_sel, ("admin" if "Manager" in user_sel else "viewer")
                db.execute("INSERT INTO audit_logs VALUES (?,?,?)", (user_sel, "Login", datetime.now().strftime("%Y-%m-%d %H:%M")))
                db.commit()
                st.rerun()
            else: st.error("Invalid PIN")
    st.stop()

# --- 4. NAVIGATION ---
if os.path.exists("logo.png"): st.sidebar.image("logo.png")
st.sidebar.write(f"👤 **{st.session_state.user_name}**")
if st.sidebar.button("Log Out"): st.session_state.clear(); st.rerun()

tab1, tab2, tab3, tab4 = st.tabs(["🏗️ Inventory", "🚚 Deliveries", "📈 Insights", "🕵️ Audit"])

# --- 5. TAB 1: INVENTORY & P.O. ENTRY ---
with tab1:
    col_l, col_r = st.columns([2, 1])
    with col_l:
        st.subheader("Live Stock Ledger")
        df_assets = pd.read_sql("SELECT * FROM assets", db)
        search = st.text_input("🔍 Search Items...")
        if not df_assets.empty:
            if search: df_assets = df_assets[df_assets['description'].str.contains(search, case=False)]
            st.dataframe(df_assets, use_container_width=True, hide_index=True)
        else: st.info("No items in inventory.")

    with col_r:
        if st.session_state.role == "admin":
            with st.expander("➕ Update Stock / Log P.O.", expanded=True):
                with st.form("entry_form", clear_on_submit=True):
                    a_id, desc = st.text_input("ID / Barcode"), st.text_input("Description")
                    qty = st.number_input("Quantity", step=1)
                    supp, price = st.text_input("Supplier"), st.number_input("Unit Price (R)", step=0.01)
                    is_po = st.checkbox("Mark as Client Order (P.O.)")
                    if st.form_submit_button("Save"):
                        now = datetime.now().strftime("%Y-%m-%d %H:%M")
                        if is_po: db.execute("INSERT INTO client_orders VALUES (?,?,?,?,?,?)", ("Client", desc, qty, qty, now, "Pending"))
                        else:
                            db.execute("INSERT INTO assets VALUES (?,?,?,?) ON CONFLICT(asset_id) DO UPDATE SET qty=qty+excluded.qty, last_updated=excluded.last_updated", (a_id, desc, qty, now))
                            db.execute("INSERT INTO history VALUES (?,?,?,?,?,?)", (desc, qty, now, supp, price, st.session_state.user_name))
                        db.commit(); st.success("Updated Successfully"); st.rerun()

# --- 6. TAB 2: DELIVERY TRACKER ---
with tab2:
    st.subheader("Active Deliveries")
    orders = pd.read_sql("SELECT rowid as ID, * FROM client_orders WHERE status != 'Complete'", db)
    if not orders.empty:
        st.dataframe(orders, use_container_width=True, hide_index=True)
        with st.expander("Log Delivery (Partial or Full)"):
            sel_id = st.number_input("Order ID", min_value=1)
            del_qty = st.number_input("Qty Delivered", min_value=1)
            if st.button("Confirm Delivery"):
                db.execute("UPDATE client_orders SET qty_remaining = qty_remaining - ?, status = CASE WHEN qty_remaining <= ? THEN 'Complete' ELSE 'Partial' END WHERE rowid = ?", (del_qty, del_qty, sel_id))
                db.commit(); st.success("Delivery Tracked"); st.rerun()
    else: st.info("No pending client orders.")

# --- 7. TAB 3: PROCUREMENT INSIGHTS ---
with tab3:
    st.subheader("📊 Business Intelligence")
    hist_df = pd.read_sql("SELECT item_desc, SUM(qty_added) as Total, AVG(unit_price) as AvgPrice FROM history GROUP BY item_desc ORDER BY Total DESC", db)
    if not hist_df.empty:
        st.write("### High Turnover (Petrol Savers)")
        st.bar_chart(hist_df.set_index('item_desc')['Total'])
        st.write("### Purchase Pricing History")
        st.table(hist_df)
    else: st.info("Procurement data will appear here once purchases are logged.")

# --- 8. TAB 4: AUDIT LOGS ---
with tab4:
    st.subheader("🕵️ System Activity")
    logs = pd.read_sql("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 20", db)
    st.table(logs)