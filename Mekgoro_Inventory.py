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
    .alert { background-color: #fff3cd; padding: 12px; border-radius: 6px; margin: 10px 0; }
    .supplier-card { background-color: #e8f5e9; padding: 12px; border-radius: 6px; margin: 10px 0; }
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
# LOAD ITEMS - Improved detection & debug
# ────────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_items():
    file_path = "ItemListingReport.xlsx"
    
    if not os.path.exists(file_path):
        st.error("❌ ItemListingReport.xlsx NOT FOUND in app folder. Please upload it to your repository.")
        return []
    
    try:
        df = pd.read_excel(file_path, dtype=str)
        
        # Show columns for debugging
        st.markdown("**Debug: Excel columns found**")
        st.write(list(df.columns))
        
        # Flexible column detection
        possible_cols = [col for col in df.columns 
                        if any(kw in str(col).lower() for kw in ['desc', 'description', 'product', 'item', 'name'])]
        
        if possible_cols:
            desc_col = possible_cols[0]
            st.success(f"Using column: **{desc_col}** for item names")
            items = df[desc_col].dropna().astype(str).str.strip().unique().tolist()
            valid = [i for i in items if i and len(i) > 3 and "cement" not in i.lower()]
            if valid:
                st.write(f"Loaded **{len(valid)}** real items")
                return sorted(valid)
        
        st.error("Could not find a description/product column. Please check column names above.")
        return []
    
    except Exception as e:
        st.error(f"Failed to read Excel: {str(e)}")
        return []

items_list = load_items()

# ────────────────────────────────────────────────
# SUPPLIER FUNCTIONS
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
        """, (name.strip(), contact_person, phone, email, address, vat_number, bank_account, bank_branch, swift_code, notes, now))
        db.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # duplicate

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
    "📊 Inventory & Alerts",
    "📦 Receive Goods",
    "🛒 Purchase Orders",
    "📤 Sell / Client PO",
    "📜 History",
    "⚙️ Backup",
    "🏢 Suppliers"
])

# ────────────────────────────────────────────────
# HELPERS
# ────────────────────────────────────────────────
def get_current_qty(item_name):
    res = pd.read_sql("SELECT qty FROM assets WHERE item_name = ?", db, params=(item_name,))
    return res.iloc[0]['qty'] if not res.empty else 0

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
# TAB 1: INVENTORY + ALERTS
# ────────────────────────────────────────────────
with tab1:
    st.subheader("Current Stock")
    df = pd.read_sql("SELECT * FROM assets ORDER BY item_name", db)
    
    if df.empty:
        st.info("No stock recorded yet.")
    else:
        def highlight_low(row):
            if row['qty'] <= 0:
                return ['background-color: #ffebee'] * len(row)
            if row['qty'] <= 10:
                return ['background-color: #fff3cd'] * len(row)
            return [''] * len(row)
        
        st.dataframe(
            df.style.apply(highlight_low, axis=1).format({"qty": "{:,.0f}"}),
            use_container_width=True
        )

    st.subheader("Low Stock Alerts")
    low = df[df['qty'] <= 10]
    if low.empty:
        st.success("No low stock items.")
    else:
        for _, row in low.iterrows():
            st.markdown(f"""
                <div class="alert">
                <strong>{row['item_name']}</strong>: {row['qty']:,} units (updated {row['last_update']})
                </div>
            """, unsafe_allow_html=True)

# ────────────────────────────────────────────────
# TAB 2: RECEIVE GOODS – Multi-line + Supplier contact
# ────────────────────────────────────────────────
with tab2:
    st.subheader("Receive Goods from Supplier")
    
    suppliers_list = get_suppliers()
    if not suppliers_list:
        st.warning("No suppliers added yet. Go to Suppliers tab → Add New Supplier first.")
    
    with st.form("receive_form"):
        supplier_name = st.selectbox("Select Supplier", suppliers_list if suppliers_list else ["No suppliers yet"])
        
        if supplier_name and supplier_name != "No suppliers yet":
            sup = pd.read_sql("SELECT * FROM suppliers WHERE name = ?", db, params=(supplier_name,))
            if not sup.empty:
                r = sup.iloc[0]
                st.markdown(f"""
                    <div class="supplier-card">
                    <strong>{r['name']}</strong><br>
                    Phone: {r['phone'] or '—'}<br>
                    Email: {r['email'] or '—'}<br>
                    Address: {r['address'] or '—'}<br>
                    VAT: {r['vat_number'] or '—'}<br>
                    Bank: {r['bank_account'] or '—'} ({r['bank_branch'] or ''})<br>
                    SWIFT: {r['swift_code'] or '—'}
                    </div>
                """, unsafe_allow_html=True)
        
        ref = st.text_input("Invoice / SO / Delivery Ref (e.g. ION127436)")
        
        col1, col2 = st.columns(2)
        with col1:
            item = st.selectbox("Item", items_list if items_list else ["No items loaded – check Excel"])
        with col2:
            qty = st.number_input("Received Quantity", min_value=1, step=1)
        
        if st.form_submit_button("Receive"):
            if not items_list:
                st.error("No items available. Please fix ItemListingReport.xlsx loading.")
            elif not supplier_name or supplier_name == "No suppliers yet":
                st.error("Please select a supplier first.")
            else:
                update_stock_and_log(item, qty, "receive", ref, supplier_name)
                st.success(f"Received {qty:,} × {item} from {supplier_name}")
                st.rerun()

# ────────────────────────────────────────────────
# TAB 7: SUPPLIERS – Add / View
# ────────────────────────────────────────────────
with tab7:
    st.subheader("Manage Suppliers")
    
    with st.form("add_supplier"):
        name = st.text_input("Supplier Name *", placeholder="OMNISURGE (PTY) LTD")
        contact_person = st.text_input("Contact Person")
        phone = st.text_input("Phone", placeholder="+27 21 551 3655")
        email = st.text_input("Email", placeholder="queries@omnisurge.co.za")
        address = st.text_area("Address", placeholder="Unit 3, Radio Park, Marconi Road, Montague Gardens, Cape Town")
        vat_number = st.text_input("VAT Number", placeholder="2007/004914/07")
        bank_account = st.text_input("Bank Account Number")
        bank_branch = st.text_input("Branch Code")
        swift_code = st.text_input("SWIFT Code", placeholder="FIRNZAJJ")
        notes = st.text_area("Notes")
        
        if st.form_submit_button("Add Supplier"):
            if not name.strip():
                st.error("Name is required")
            elif add_supplier(name.strip(), contact_person, phone, email, address, vat_number, bank_account, bank_branch, swift_code, notes):
                st.success(f"Added: {name}")
            else:
                st.error("Supplier name already exists")
            st.rerun()
    
    st.subheader("Existing Suppliers")
    sup_df = pd.read_sql("SELECT name, phone, email, vat_number FROM suppliers ORDER BY name", db)
    if sup_df.empty:
        st.info("No suppliers yet. Add one above.")
    else:
        st.dataframe(sup_df, use_container_width=True)

# ────────────────────────────────────────────────
# Remaining tabs (add as needed from previous versions)
# Sell, Purchase Orders, History, Backup
# ────────────────────────────────────────────────
# ... paste here if you want them back

# SIDEBAR
with st.sidebar:
    st.markdown("### MEKGORO CONSULTING")
    st.write(f"**User:** {st.session_state.user}")
    if st.button("Logout"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
