import streamlit as st
import sqlite3
import pandas as pd
import re
from datetime import datetime
from difflib import get_close_matches # Helps with fuzzy name matching

# --- 1. DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('price_monitor_v4.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT UNIQUE)')
    c.execute('''CREATE TABLE IF NOT EXISTS products 
                 (id INTEGER PRIMARY KEY, name TEXT, description TEXT, category_id INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS listings 
                 (id INTEGER PRIMARY KEY, product_id INTEGER, shop_name TEXT, 
                  price REAL, url TEXT, last_updated TEXT)''')
    conn.commit()
    return conn

# --- 2. DATA UTILITIES ---
def get_incoming_data():
    params = st.query_params
    inc_name = params.get("name", "")
    inc_url = params.get("url", "")
    inc_price_raw = params.get("price", "0")
    
    clean_p = 0.0
    try:
        p_match = re.search(r"[\d,.]+", inc_price_raw)
        if p_match:
            clean_p = float(p_match.group().replace(',', ''))
    except: pass
    
    return inc_name, inc_url, clean_p

# --- 3. UI CONFIG ---
st.set_page_config(page_title="PricePro Matcher", layout="wide")
conn = init_db()
inc_name, inc_url, inc_price = get_incoming_data()

tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "➕ Add/Update Listing", "📁 Categories"])

# --- TAB 3: CATEGORIES ---
with tab3:
    st.subheader("Manage Categories")
    col_cat1, col_cat2 = st.columns([2, 1])
    with col_cat1:
        new_cat = st.text_input("New Category Name")
    with col_cat2:
        if st.button("Add Category") and new_cat:
            conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (new_cat,))
            conn.commit()
            st.rerun()

# --- TAB 2: ADD/UPDATE ---
with tab2:
    prods_df = pd.read_sql_query("SELECT * FROM products", conn)
    prod_map = dict(zip(prods_df['name'], prods_df['id']))
    
    # FUZZY MATCHING LOGIC
    # If a name comes from the browser, find the closest match in our DB
    best_match = None
    if inc_name and not prods_df.empty:
        matches = get_close_matches(inc_name, prods_df['name'].tolist(), n=1, cutoff=0.3)
        if matches:
            best_match = matches[0]

    st.subheader("Assign Price to Product")
    if best_match:
        st.info(f"🔍 Found a potential match: **{best_match}**")
    
    target_prod = st.selectbox(
        "Which product is this for?", 
        ["(Create New Product)"] + list(prod_map.keys()),
        index=list(prod_map.keys()).index(best_match) + 1 if best_match else 0
    )
    
    if target_prod == "(Create New Product)":
        col1, col2 = st.columns(2)
        prod_name = col1.text_input("Master Product Name", value=inc_name)
        prod_desc = col1.text_area("Description")
        
        cats = pd.read_sql_query("SELECT * FROM categories", conn)
        cat_map = dict(zip(cats['name'], cats['id']))
        prod_cat = col2.selectbox("Category", options=list(cat_map.keys()))
        cat_id = cat_map.get(prod_cat)
    else:
        p_info = prods_df[prods_df['id'] == prod_map[target_prod]].iloc[0]
        prod_name = p_info['name']
        cat_id = p_info['category_id']

    st.divider()
    
    col_a, col_b, col_c = st.columns([1, 2, 1])
    # Identify store from URL automatically
    detected_store = "Shop"
    if "lazada" in inc_url.lower(): detected_store = "Lazada"
    elif "shopee" in inc_url.lower(): detected_store = "Shopee"
    elif "amazon" in inc_url.lower(): detected_store = "Amazon"

    store = col_a.text_input("Store Name", value=detected_store)
    link = col_b.text_input("Product URL", value=inc_url)
    price_input = col_c.number_input("Price", value=inc_price, format="%.2f")
    
    if st.button("🚀 Save Listing"):
        today = datetime.now().strftime("%Y-%m-%d")
        c = conn.cursor()
        if target_prod == "(Create New Product)":
            c.execute("INSERT INTO products (name, description, category_id) VALUES (?, ?, ?)", 
                      (prod_name, prod_desc, cat_id))
            p_id = c.lastrowid
        else:
            p_id = prod_map[target_prod]
            
        # Update or Insert listing
        existing = pd.read_sql_query(f"SELECT id FROM listings WHERE product_id={p_id} AND shop_name='{store}'", conn)
        if not existing.empty:
            c.execute("UPDATE listings SET price=?, url=?, last_updated=? WHERE id=?", (price_input, link, today, existing.iloc[0]['id']))
        else:
            c.execute("INSERT INTO listings (product_id, shop_name, price, url, last_updated) VALUES (?,?,?,?,?)", (p_id, store, price_input, link, today))
        
        conn.commit()
        st.success("Listing Updated!")
        st.query_params.clear()

# --- TAB 1: DASHBOARD ---
with tab1:
    search_q = st.text_input("🔍 Search Dashboard...")
    
    query = "SELECT p.*, c.name as cat_name FROM products p LEFT JOIN categories c ON p.category_id = c.id"
    if search_q: query += f" WHERE p.name LIKE '%{search_q}%'"
    
    display_df = pd.read_sql_query(query, conn)
    
    for _, prod in display_df.iterrows():
        with st.container(border=True):
            header_col, del_col = st.columns([5, 1])
            header_col.subheader(f"{prod['name']} ({prod['cat_name']})")
            
            # DELETE PRODUCT BUTTON
            if del_col.button("🗑️", key=f"del_{prod['id']}"):
                conn.execute(f"DELETE FROM products WHERE id={prod['id']}")
                conn.execute(f"DELETE FROM listings WHERE product_id={prod['id']}")
                conn.commit()
                st.rerun()

            listings = pd.read_sql_query(f"SELECT * FROM listings WHERE product_id={prod['id']} ORDER BY price ASC", conn)
            if not listings.empty:
                st.success(f"Best Deal: ₱{listings.iloc[0]['price']:,.2f} at {listings.iloc[0]['shop_name']}")
                for _, lst in listings.iterrows():
                    l1, l2, l3, l4 = st.columns([2, 1, 2, 1])
                    l1.write(f"🏪 {lst['shop_name']}")
                    l2.write(f"₱{lst['price']:,.2f}")
                    l3.write(f"📅 {lst['last_updated']}")
                    l4.link_button("View", lst['url'])
