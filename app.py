import streamlit as st
import sqlite3
import pandas as pd
import re
from datetime import datetime
from difflib import get_close_matches

# --- 1. DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('price_monitor_v19.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT UNIQUE)')
    c.execute('''CREATE TABLE IF NOT EXISTS products 
                 (id INTEGER PRIMARY KEY, name TEXT, description TEXT, 
                  category_id INTEGER, target_price REAL DEFAULT 0, 
                  is_bought INTEGER DEFAULT 0, final_paid REAL DEFAULT 0, shipping_fee REAL DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS listings 
                 (id INTEGER PRIMARY KEY, product_id INTEGER, shop_name TEXT, 
                  price REAL, url TEXT, last_updated TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS history 
                 (id INTEGER PRIMARY KEY, product_id INTEGER, shop_name TEXT, 
                  price REAL, date TEXT)''')
    
    default_cats = ["Tech & Gadgets", "Home & Living", "Health & Beauty", "Groceries", "Fashion"]
    for cat in default_cats:
        c.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat,))
    conn.commit()
    return conn

conn = init_db()
st.set_page_config(page_title="PricePro v19", layout="wide")

# --- 2. CAPTURE URL PARAMETERS ---
params = st.query_params
inc = {
    "name": params.get("name", ""),
    "url": params.get("url", ""),
    "price": params.get("price", "0"),
    "img": params.get("img", ""), # --- UPDATED: New field
    "tab_req": params.get("tab", "dashboard")
}

# --- 3. SIDEBAR NAVIGATION ---
nav_index = 1 if inc['tab_req'] == 'add' else 0
st.sidebar.title("💰 PricePro")
page = st.sidebar.radio("Navigation", ["📊 Dashboard", "➕ Add/Update Listing", "📁 Categories"], index=nav_index)

# --- PAGE: CATEGORIES (Omitted for brevity, keep your original) ---
if page == "📁 Categories":
    # ... (keep your existing category code here)
    pass

# --- PAGE: ADD/UPDATE ---
elif page == "➕ Add/Update Listing":
    st.header("Add or Update Listing")
    
    # --- UPDATED: Visual Preview Section ---
    if inc['img']:
        with st.container(border=True):
            cols = st.columns([1, 4])
            cols[0].image(inc['img'], width=150)
            cols[1].markdown(f"**Extracting Data for:**\n{inc['name']}")

    prods_df = pd.read_sql_query("SELECT * FROM products WHERE is_bought=0", conn)
    prod_map = dict(zip(prods_df['name'], prods_df['id']))
    
    matches = get_close_matches(inc['name'], list(prod_map.keys()), n=1, cutoff=0.2) if inc['name'] and prod_map else []
    best_match = matches[0] if matches else None

    target_prod = st.selectbox("Assign to Product Folder", ["(Create New Product)"] + list(prod_map.keys()),
                                index=list(prod_map.keys()).index(best_match) + 1 if best_match else 0)
    
    if target_prod == "(Create New Product)":
        col1, col2 = st.columns(2)
        prod_name = col1.text_input("Master Product Name", value=inc['name'])
        target_val = col1.number_input("Target Price (Goal)", value=0.0)
        prod_desc = col2.text_area("Notes / Specs")
        cats = pd.read_sql_query("SELECT * FROM categories", conn)
        cat_options = cats['name'].tolist() if not cats.empty else ["None"]
        cat_selection = col2.selectbox("Category", options=cat_options)
        cat_id = pd.read_sql_query(f"SELECT id FROM categories WHERE name='{cat_selection}'", conn).iloc[0][0] if not cats.empty else None
    else:
        p_info = prods_df[prods_df['id'] == prod_map[target_prod]].iloc[0]
        prod_name, target_val = p_info['name'], p_info['target_price']
        st.info(f"Adding listing to existing product: **{prod_name}**")

    st.divider()
    ca, cb, cc = st.columns([1, 2, 1])
    store_val = "Lazada" if "lazada" in inc['url'].lower() else "Shopee" if "shopee" in inc['url'].lower() else "Shop"
    store = ca.text_input("Store Name", value=store_val)
    link = cb.text_input("URL", value=inc['url'])
    
    try: 
        p_val = float(re.sub(r'[^\d.]', '', inc['price'].replace(',','')))
    except: 
        p_val = 0.0
    
    price = cc.number_input("Current Price", value=p_val, min_value=0.0, step=0.01)

    if price <= 0:
        st.warning("⚠️ Price must be greater than zero to save.")
        save_disabled = True
    else:
        save_disabled = False
    
    if st.button("🚀 Save Listing", disabled=save_disabled):
        today = datetime.now().strftime("%Y-%m-%d")
        c = conn.cursor()
        if target_prod == "(Create New Product)":
            c.execute("INSERT INTO products (name, description, category_id, target_price) VALUES (?, ?, ?, ?)", (prod_name, prod_desc, cat_id, target_val))
            p_id = c.lastrowid
        else: p_id = prod_map[target_prod]
        
        c.execute("INSERT OR REPLACE INTO listings (product_id, shop_name, price, url, last_updated) VALUES (?,?,?,?,?)", (p_id, store, price, link, today))
        c.execute("INSERT INTO history (product_id, shop_name, price, date) VALUES (?,?,?,?)", (p_id, store, price, today))
        conn.commit()
        st.success("Successfully saved!")
        st.query_params.clear()

# --- PAGE: DASHBOARD (Omitted for brevity, keep your original) ---
elif page == "📊 Dashboard":
    # ... (keep your existing dashboard code here)
    pass
