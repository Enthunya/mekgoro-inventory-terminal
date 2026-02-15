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
    .supplier-info { background-color: #e8f5e9; padding: 12px; border-radius: 6px; margin: 10px 0; }
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
            supplier TEXT,
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
            status TEXT DEFAULT 'Open',
            created_date TEXT,
            expected_date TEXT
        )
    """)
    # NEW: Suppliers table with full contact info
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
    db.commit()

init_db()

# ────────────────────────────────────────────────
# GOOGLE DRIVE AUTH (unchanged)
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
    file_path = "ItemListingReport.xlsx"
    fallback = ["Cement 50kg", "Sand", "Stone", "Bricks", "Steel Bars"]
    if not os.path.exists(file_path):
        return sorted(fallback)
    try:
        df = pd.read_excel(file_path)
        desc_col = next((col for col in df.columns if 'description' in col.lower()), None)
        if desc_col:
            items = df[desc_col].dropna().astype(str).unique().tolist()
            return sorted([item.strip() for item in items if item.strip()])
        return sorted(fallback)
    except Exception as e:
        st.error(f"Error reading items: {e}")
        return sorted(fallback)

items_list = load_items()

# ────────────────────────────────────────────────
# LOAD SUPPLIERS FROM DB
# ────────────────────────────────────────────────
def get_suppliers():
    df = pd.read_sql("SELECT name FROM suppliers ORDER BY name", db)
    return df['name'].tolist() if not df.empty else []

def add_supplier(name, contact_person="", phone="", email="", address="", vat_number="", bank_account="", bank_branch="", swift_code="", notes=""):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        db.execute("""
            INSERT INTO suppliers (name, contact_person, phone, email, address, vat_number, bank_account, bank_branch, swift_code, notes, added_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, contact_person, phone, email, address, vat_number, bank_account, bank_branch, swift_code, notes, now))
        db.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # duplicate name

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

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📊 Inventory",
    "📦 Receive Goods",
    "🛒 Purchase Orders",
    "📤 Sell / Client PO",
    "📜 History",
    "⚙️ Backup",
    "🏢 Suppliers"
])

# ────────────────────────────────────────────────
# HELPERS (unchanged except for supplier logging)
# ────────────────────────────────────────────────
def update_stock_and_log(item, qty_change, action_type, reference="", supplier=""):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db.execute("""
        INSERT OR REPLACE INTO assets (item_name, qty, last_update)
        VALUES (?, COALESCE((SELECT qty FROM assets WHERE item_name=?), 0) + ?, ?)
    """, (item, item, qty_change, now))
    db.execute("""
        INSERT INTO logs (type, item_name, qty, user, reference, supplier, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (action_type, item, qty_change, st.session_state.user, reference, supplier, now))
    db.commit()

# ────────────────────────────────────────────────
# TAB 1: INVENTORY (unchanged for brevity)
# ────────────────────────────────────────────────
with tab1:
    st.subheader("Current Stock")
    df = pd.read_sql("SELECT * FROM assets ORDER BY item_name", db)
    st.dataframe(df, use_container_width=True)

# ────────────────────────────────────────────────
# TAB 2: RECEIVE GOODS – Supplier dropdown + contact display
# ────────────────────────────────────────────────
with tab2:
    st.subheader("Receive Goods from Supplier")
    
    suppliers_list = get_suppliers()
    if not suppliers_list:
        st.warning("No suppliers in database yet. Add them in the Suppliers tab first.")
    
    with st.form("receive_form"):
        supplier_name = st.selectbox("Select Supplier", suppliers_list if suppliers_list else ["Add new supplier first"])
        
        if supplier_name and supplier_name != "Add new supplier first":
            sup_info = pd.read_sql("SELECT * FROM suppliers WHERE name = ?", db, params=(supplier_name,))
            if not sup_info.empty:
                row = sup_info.iloc[0]
                st.markdown(f"""
                    <div class="supplier-info">
                    <strong>{row['name']}</strong><br>
                    Contact: {row['contact_person'] or 'N/A'}<br>
                    Phone: {row['phone'] or 'N/A'}<br>
                    Email: {row['email'] or 'N/A'}<br>
                    Address: {row['address'] or 'N/A'}<br>
                    VAT: {row['vat_number'] or 'N/A'}<br>
                    Bank: {row['bank_account'] or 'N/A'} ({row['bank_branch'] or ''})<br>
                    SWIFT: {row['swift_code'] or 'N/A'}
                    </div>
                """, unsafe_allow_html=True)
        
        ref = st.text_input("Invoice / SO / Delivery Ref")
        item = st.selectbox("Item", items_list)
        qty = st.number_input("Received Quantity", min_value=1)
        
        if st.form_submit_button("Receive"):
            if not supplier_name or supplier_name == "Add new supplier first":
                st.error("Please select or add a supplier first.")
            else:
                update_stock_and_log(item, qty, "receive", ref, supplier_name)
                st.success(f"Received {qty} × {item} from {supplier_name}")
                st.rerun()

# ────────────────────────────────────────────────
# TAB 7: SUPPLIERS (NEW – Add / View full contact info)
# ────────────────────────────────────────────────
with tab7:
    st.subheader("Manage Suppliers")
    
    tab_add, tab_view = st.tabs(["Add New Supplier", "View / List"])
    
    with tab_add:
        with st.form("add_supplier_form"):
            name = st.text_input("Supplier Name *", placeholder="e.g. OMNISURGE (PTY) LTD")
            contact_person = st.text_input("Contact Person")
            phone = st.text_input("Phone", placeholder="+27 21 551 3655")
            email = st.text_input("Email", placeholder="queries@omnisurge.co.za")
            address = st.text_area("Physical Address", placeholder="Unit 3, Radio Park, Marconi Road, Montague Gardens, Cape Town")
            vat_number = st.text_input("VAT Number", placeholder="2007/004914/07")
            bank_account = st.text_input("Bank Account Number")
            bank_branch = st.text_input("Branch Code")
            swift_code = st.text_input("SWIFT Code", placeholder="FIRNZAJJ")
            notes = st.text_area("Notes / Payment Instructions")
            
            if st.form_submit_button("Add Supplier"):
                if not name.strip():
                    st.error("Supplier Name is required.")
                elif add_supplier(name.strip(), contact_person, phone, email, address, vat_number, bank_account, bank_branch, swift_code, notes):
                    st.success(f"Supplier '{name}' added successfully!")
                else:
                    st.error("Supplier name already exists.")
                st.rerun()
    
    with tab_view:
        sup_df = pd.read_sql("SELECT * FROM suppliers ORDER BY name", db)
        if sup_df.empty:
            st.info("No suppliers added yet. Use the 'Add New Supplier' tab.")
        else:
            st.dataframe(sup_df, use_container_width=True)

# ────────────────────────────────────────────────
# Other tabs (Purchase Orders, Sell, History, Backup) – add them as before
# ... (copy from previous working version if needed)
