import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
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
    .alert { background-color: #fff3cd; padding: 12px; border-radius: 6px; margin: 10px 0; }
    .warning { background-color: #ffebee; padding: 12px; border-radius: 6px; margin: 10px 0; }
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
            type TEXT,                  -- 'receive', 'out', 'adjust'
            item_name TEXT,
            qty INTEGER,
            user TEXT,
            reference TEXT,             -- invoice/PO number
            client_or_supplier TEXT,
            timestamp TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            contact_person TEXT,
            phone TEXT,
            email TEXT,
            address TEXT,
            vat_number TEXT,
            bank_account TEXT,
            bank_branch TEXT,
            swift_code TEXT,
            notes TEXT,
            added_date TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS known_items (
            canonical_name TEXT PRIMARY KEY,
            added_date TEXT,
            notes TEXT
        )
    """)
    db.commit()

init_db()

# ────────────────────────────────────────────────
# GOOGLE DRIVE AUTH
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
        st.error(f"Google Drive connection failed: {e}")

# ────────────────────────────────────────────────
# LOAD KNOWN ITEMS & SUPPLIERS
# ────────────────────────────────────────────────
def get_known_items():
    df = pd.read_sql("SELECT canonical_name FROM known_items ORDER BY canonical_name", db)
    return df['canonical_name'].tolist() if not df.empty else []

def add_known_item(name):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute("INSERT OR IGNORE INTO known_items (canonical_name, added_date) VALUES (?, ?)", (name.strip(), now))
    db.commit()

def get_suppliers():
    df = pd.read_sql("SELECT name FROM suppliers ORDER BY name", db)
    return df['name'].tolist() if not df.empty else []

# ────────────────────────────────────────────────
# LOGIN
# ────────────────────────────────────────────────
if "user" not in st.session_state:
    st.title("🛡️ Mekgoro Secure Login")
    name = st.selectbox("Select User:", ["Ndule", "Biino", "Anthony", "Mike"])
    if st.button("Enter Terminal"):
        st.session_state.user = name
        st.rerun()
    st.stop()

# ────────────────────────────────────────────────
# MAIN DASHBOARD
# ────────────────────────────────────────────────
st.image("logo.png", width=380)
st.markdown("<h3 style='text-align: center; color: #006400;'>MEKGORO CONSULTING</h3>", unsafe_allow_html=True)
st.title(f"🏗️ Mekgoro Terminal | {st.session_state.user}")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Inventory",
    "📦 Receive Goods",
    "📤 Goods Out / Delivery",
    "📜 History",
    "🏢 Suppliers & Items"
])

# ────────────────────────────────────────────────
# HELPERS
# ────────────────────────────────────────────────
def get_current_qty(item_name):
    res = pd.read_sql("SELECT qty FROM assets WHERE item_name = ?", db, params=(item_name,))
    return res.iloc[0]['qty'] if not res.empty else 0

def update_stock_and_log(item, qty_change, action_type, reference="", client_or_supplier=""):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute("""
        INSERT OR REPLACE INTO assets (item_name, qty, last_update)
        VALUES (?, COALESCE((SELECT qty FROM assets WHERE item_name=?), 0) + ?, ?)
    """, (item.strip(), item.strip(), qty_change, now))
    
    db.execute("""
        INSERT INTO logs (type, item_name, qty, user, reference, client_or_supplier, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (action_type, item.strip(), qty_change, st.session_state.user, reference, client_or_supplier, now))
    db.commit()

# ────────────────────────────────────────────────
# TAB 1: INVENTORY
# ────────────────────────────────────────────────
with tab1:
    st.subheader("Current Stock")
    df = pd.read_sql("SELECT * FROM assets ORDER BY item_name", db)
    
    if df.empty:
        st.info("No stock recorded yet.")
    else:
        def highlight(row):
            if row['qty'] <= 0: return ['background-color: #ffebee'] * len(row)
            if row['qty'] <= 10: return ['background-color: #fff3cd'] * len(row)
            return [''] * len(row)
        
        st.dataframe(df.style.apply(highlight, axis=1).format({"qty": "{:,.0f}"}), use_container_width=True)

# ────────────────────────────────────────────────
# TAB 2: RECEIVE GOODS
# ────────────────────────────────────────────────
with tab2:
    st.subheader("Receive Goods from Supplier")
    
    suppliers_list = get_suppliers()
    known_items = get_known_items()
    
    with st.form("receive_form"):
        supplier = st.selectbox("Supplier", suppliers_list if suppliers_list else ["Add supplier first"])
        ref = st.text_input("Invoice / SO / Delivery Ref")
        item_input = st.text_input("Item Description", key="receive_item")
        
        final_item = item_input.strip()
        if final_item and final_item not in known_items:
            if st.checkbox("Add this as new known item", value=True):
                add_known_item(final_item)
        
        qty = st.number_input("Received Quantity", min_value=1, step=1)
        
        if st.form_submit_button("Receive"):
            if not final_item:
                st.error("Enter item description")
            elif not supplier or supplier == "Add supplier first":
                st.error("Select a supplier")
            else:
                update_stock_and_log(final_item, qty, "receive", ref, supplier)
                st.success(f"Received {qty:,} × {final_item}")
                st.rerun()

# ────────────────────────────────────────────────
# TAB 3: GOODS OUT / DELIVERY (NEW & IMPROVED)
# ────────────────────────────────────────────────
with tab3:
    st.subheader("Goods Leaving Storage (Delivery / Sale)")
    st.info("Use this when goods are taken out of storage for clients, deliveries, or sales.")
    
    known_items = get_known_items()
    
    with st.form("out_form"):
        item_input = st.text_input("Item Description", key="out_item")
        
        final_item = item_input.strip()
        if final_item and final_item not in known_items:
            if st.checkbox("Add this as new known item", value=True):
                add_known_item(final_item)
        
        current_stock = get_current_qty(final_item) if final_item else 0
        st.metric("Current Stock", f"{current_stock:,}")
        
        qty_out = st.number_input("Quantity Leaving", min_value=1, step=1)
        client_name = st.text_input("Client Name / Site")
        client_ref = st.text_input("Client PO / Order Reference")
        
        if st.form_submit_button("Confirm Goods Out"):
            if not final_item:
                st.error("Enter item description")
            elif current_stock < qty_out:
                st.error(f"**Not enough stock!** Only {current_stock:,} available. Cannot release {qty_out:,} units.")
            else:
                update_stock_and_log(final_item, -qty_out, "out", client_ref, client_name)
                st.success(f"Goods out recorded: {qty_out:,} × {final_item} to {client_name or 'Unknown'} (Ref: {client_ref or 'N/A'})")
                st.rerun()

# ────────────────────────────────────────────────
# TAB 4: HISTORY
# ────────────────────────────────────────────────
with tab4:
    st.subheader("Transaction History")
    logs = pd.read_sql("SELECT * FROM logs ORDER BY timestamp DESC LIMIT 200", db)
    st.dataframe(logs, use_container_width=True)

# ────────────────────────────────────────────────
# TAB 5: SUPPLIERS & ITEMS
# ────────────────────────────────────────────────
with tab5:
    tab_s, tab_i = st.tabs(["Suppliers", "Known Items"])
    
    with tab_s:
        st.subheader("Add Supplier")
        with st.form("add_supplier"):
            name = st.text_input("Name")
            phone = st.text_input("Phone")
            email = st.text_input("Email")
            address = st.text_area("Address")
            vat = st.text_input("VAT")
            if st.form_submit_button("Add"):
                if add_supplier(name, phone=phone, email=email, address=address, vat_number=vat):
                    st.success("Added")
                else:
                    st.error("Name already exists")
    
    with tab_i:
        st.subheader("Known Items")
        items_df = pd.read_sql("SELECT canonical_name FROM known_items ORDER BY canonical_name", db)
        st.dataframe(items_df, use_container_width=True)

# ────────────────────────────────────────────────
# SIDEBAR
# ────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### MEKGORO CONSULTING")
    st.write(f"User: {st.session_state.user}")
    if st.button("Logout"):
        del st.session_state["user"]
        st.rerun()
