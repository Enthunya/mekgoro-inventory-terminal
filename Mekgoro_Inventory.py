import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ────────────────────────────────────────────────
# PAGE CONFIG + STYLING
# ────────────────────────────────────────────────
st.set_page_config(page_title="Mekgoro Inventory", page_icon="logo.png", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #f8f9fa; }
    .stButton > button { background-color: #006400; color: white; border: none; }
    .stButton > button:hover { background-color: #228B22; }
    .stSidebar { background-color: #f0f7f0; }
    h1, h2, h3 { color: #006400; }
    </style>
""", unsafe_allow_html=True)

# ────────────────────────────────────────────────
# DATABASE SETUP
# ────────────────────────────────────────────────
db = sqlite3.connect("mekgoro_database.db", check_same_thread=False)

def init_db():
    db.execute("""
        CREATE TABLE IF NOT EXISTS assets (
            item_name TEXT PRIMARY KEY,
            qty INTEGER DEFAULT 0,
            last_update TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            item_name TEXT,
            qty INTEGER,
            user TEXT,
            reference TEXT,
            timestamp TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS purchase_orders (
            po_id INTEGER PRIMARY KEY AUTOINCREMENT,
            po_number TEXT UNIQUE,
            supplier TEXT,
            item_name TEXT,
            qty_ordered INTEGER,
            qty_received INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Open',  -- Open, Partial, Closed
            created_date TEXT,
            expected_date TEXT
        )
    """)
    db.commit()

init_db()

# ────────────────────────────────────────────────
# GOOGLE DRIVE AUTH (for backup)
# ────────────────────────────────────────────────
drive_service = None
if "gcp_service_account" in st.secrets:
    try:
        info = dict(st.secrets["gcp_service_account"])
        key = info.get("private_key", "").replace("\\n", "\n").replace("\r\n", "\n").replace("\\\\n", "\n")
        if not key.startswith("-----BEGIN PRIVATE KEY-----"):
            key = "-----BEGIN PRIVATE KEY-----\n" + key + "\n-----END PRIVATE KEY-----"
        info["private_key"] = key
        credentials = service_account.Credentials.from_service_account_info(info, scopes=['https://www.googleapis.com/auth/drive.file'])
        drive_service = build('drive', 'v3', credentials=credentials)
    except Exception as e:
        st.error(f"Google Drive failed: {e}")

# ────────────────────────────────────────────────
# LOAD ITEMS
# ────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_items():
    file = "ItemListingReport.xlsx"
    fallback = ["Cement 50kg", "Sand", "Stone"]
    if not os.path.exists(file):
        return sorted(fallback)
    try:
        df = pd.read_excel(file)
        col = next((c for c in df.columns if 'description' in str(c).lower()), None)
        if col:
            return sorted(df[col].dropna().astype(str).unique().tolist())
        return sorted(fallback)
    except:
        return sorted(fallback)

items_list = load_items()

# ────────────────────────────────────────────────
# LOGIN
# ────────────────────────────────────────────────
if "user" not in st.session_state:
    st.title("🛡️ Mekgoro Secure Login")
    name = st.selectbox("User:", ["Manager", "Biino", "Anthony", "Mike"])
    if st.button("Enter"):
        st.session_state.user = name
        st.rerun()
    st.stop()

# ────────────────────────────────────────────────
# HELPERS
# ────────────────────────────────────────────────
def get_current_qty(item):
    res = pd.read_sql("SELECT qty FROM assets WHERE item_name = ?", db, params=(item,))
    return res.iloc[0]['qty'] if not res.empty else 0

def update_stock_and_log(item, qty_change, action_type, reference=""):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute("""
        INSERT OR REPLACE INTO assets (item_name, qty, last_update)
        VALUES (?, COALESCE((SELECT qty FROM assets WHERE item_name=?), 0) + ?, ?)
    """, (item, item, qty_change, now))
    db.execute("INSERT INTO logs (type, item_name, qty, user, reference, timestamp) VALUES (?,?,?,?,?,?)",
               (action_type, item, qty_change, st.session_state.user, reference, now))
    db.commit()

# ────────────────────────────────────────────────
# MAIN UI
# ────────────────────────────────────────────────
st.image("logo.png", width=380)
st.markdown("<h3 style='text-align: center; color: #006400;'>MEKGORO CONSULTING</h3>", unsafe_allow_html=True)
st.title(f"🏗️ Mekgoro Terminal | {st.session_state.user}")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Inventory",
    "📦 Receive (Supplier Invoice/GRN)",
    "🛒 Purchase Orders (to Supplier)",
    "📤 Sell / Client PO Check",
    "📜 History",
    "⚙️ Backup"
])

with tab1:
    st.subheader("Current Inventory")
    df = pd.read_sql("SELECT * FROM assets ORDER BY item_name", db)
    if df.empty:
        st.info("No stock yet.")
    else:
        def highlight(row):
            bg = '#ffebee' if row['qty'] <= 0 else '#fff3cd' if row['qty'] <= 10 else ''
            return [f'background-color: {bg}'] * len(row)
        
        st.dataframe(df.style.apply(highlight, axis=1).format({"qty": "{:,.0f}"}), use_container_width=True)

with tab2:  # Receive from Supplier (tied to PO where possible)
    st.subheader("Receive Goods (Invoice / Delivery Note)")
    with st.form("receive_form"):
        po_options = pd.read_sql("SELECT po_number || ' - ' || item_name || ' (' || (qty_ordered - qty_received) || ' pending)' AS label, po_id, item_name FROM purchase_orders WHERE status IN ('Open', 'Partial')", db)
        if not po_options.empty:
            selected = st.selectbox("Link to Open PO (recommended)", options=["None"] + po_options['label'].tolist())
            if selected != "None":
                po_row = po_options[po_options['label'] == selected].iloc[0]
                item = po_row['item_name']
                pending = pd.read_sql("SELECT qty_ordered - qty_received AS pending FROM purchase_orders WHERE po_id = ?", db, params=(po_row['po_id'],)).iloc[0]['pending']
                st.info(f"Pending on this PO: {pending}")
            else:
                item = st.selectbox("Item (manual)", items_list)
        else:
            item = st.selectbox("Item (no open POs)", items_list)
        
        qty = st.number_input("Received Quantity", min_value=1)
        ref = st.text_input("Invoice / GRN Ref")
        
        if st.form_submit_button("Receive"):
            update_stock_and_log(item, qty, "receive", ref)
            # If linked to PO, update it
            if 'po_row' in locals() and selected != "None":
                db.execute("UPDATE purchase_orders SET qty_received = qty_received + ?, status = CASE WHEN qty_received + ? >= qty_ordered THEN 'Closed' ELSE 'Partial' END WHERE po_id = ?",
                           (qty, qty, po_row['po_id']))
                db.commit()
            st.success(f"Received {qty} × {item}")
            st.rerun()

with tab3:  # Create & Manage POs to Supplier
    st.subheader("Create Purchase Order to Supplier")
    with st.form("po_form"):
        po_num = st.text_input("PO Number (unique)")
        supplier = st.text_input("Supplier Name")
        item = st.selectbox("Item", items_list)
        qty = st.number_input("Quantity Ordered", min_value=1)
        exp_date = st.date_input("Expected Delivery Date")
        if st.form_submit_button("Create PO"):
            if pd.read_sql("SELECT 1 FROM purchase_orders WHERE po_number = ?", db, params=(po_num,)).empty:
                db.execute("INSERT INTO purchase_orders (po_number, supplier, item_name, qty_ordered, created_date, expected_date) VALUES (?,?,?,?,?,?)",
                           (po_num, supplier, item, qty, datetime.now().strftime("%Y-%m-%d"), str(exp_date)))
                db.commit()
                st.success(f"PO {po_num} created for {qty} × {item}")
            else:
                st.error("PO number already exists.")
            st.rerun()

    st.subheader("Open / Partial POs")
    pos = pd.read_sql("SELECT * FROM purchase_orders WHERE status IN ('Open', 'Partial') ORDER BY created_date DESC", db)
    if pos.empty:
        st.info("No open POs.")
    else:
        st.dataframe(pos, use_container_width=True)

with tab4:  # Sell with Client PO check
    st.subheader("Sell / Fulfill Client PO")
    item = st.selectbox("Item", items_list)
    current = get_current_qty(item)
    st.info(f"Current physical stock: {current:,}")
    
    with st.form("sell_form"):
        qty = st.number_input("Client Requested Qty", min_value=1)
        client_po = st.text_input("Client PO Reference")
        if st.form_submit_button("Check & Sell"):
            if current < qty:
                st.error(f"Insufficient! Only {current:,} available.")
            else:
                update_stock_and_log(item, -qty, "sell", client_po)
                st.success(f"Sold {qty:,} × {item} (Client PO: {client_po or 'N/A'})")
                st.rerun()

with tab5:
    st.subheader("Transaction History")
    logs = pd.read_sql("SELECT * FROM logs ORDER BY timestamp DESC LIMIT 200", db)
    st.dataframe(logs, use_container_width=True)

with tab6:
    st.subheader("Backup")
    if st.button("Backup DB to Google Drive"):
        if drive_service:
            try:
                metadata = {'name': f"mekgoro_{datetime.now().strftime('%Y%m%d_%H%M')}.db"}
                media = MediaFileUpload('mekgoro_database.db')
                drive_service.files().create(body=metadata, media_body=media, fields='id').execute()
                st.success("Backup done!")
            except Exception as e:
                st.error(f"Failed: {e}")
        else:
            st.error("Drive not connected.")

# Sidebar
with st.sidebar:
    st.markdown("### MEKGORO CONSULTING")
    st.write(f"User: {st.session_state.user}")
    if st.button("Logout"):
        del st.session_state.user
        st.rerun()
