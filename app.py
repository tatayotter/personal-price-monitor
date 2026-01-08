import streamlit as st
import sqlite3
import pandas as pd
import re
from datetime import datetime
from difflib import get_close_matches

# --- 1. DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('price_monitor_v5.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT UNIQUE)')
    c.execute('''CREATE TABLE IF NOT EXISTS products 
                 (id INTEGER PRIMARY KEY, name TEXT, description TEXT, 
                  image_url TEXT, category_id INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS listings 
                 (id INTEGER PRIMARY KEY, product_id INTEGER, shop_name TEXT, 
                  price REAL, url TEXT, last_updated TEXT)''')
    conn.commit()
    return conn

# --- 2. DATA UTILITIES ---
def get_incoming_data():
    params = st.query_params
    return {
        "name": params.get("name", ""),
        "url": params.get("url", ""),
        "price": params.get("price", "0"),
        "img": params.get("img", "")
    }

# --- 3. UI CONFIG ---
st.set_page_config(page_title="PricePro Visual", layout="wide")
conn = init_db()
inc = get_incoming_data()

try:
    clean_p = float(re.search(r"[\d,.]+", inc['price']).group().replace(',', ''))
except:
    clean_p = 0.0

tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "➕ Add/Update Listing", "📁 Categories"])

# --- TAB 3: CATEGORIES ---
with tab3:
    st.subheader("Manage Categories")
    new_cat = st.text_input("New Category Name")
    if st.button("Add Category") and new_cat:
        conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (new_cat,))
        conn.commit()
        st.rerun()

# --- TAB 2: ADD/UPDATE ---
with tab2:
    prods_df = pd.read_sql_query("SELECT * FROM products", conn)
    prod_map = dict(zip(prods_df['name'], prods_df['id']))
    
    # Fuzzy Matching
    best_match = None
    if inc['name'] and not prods_df.empty:
        matches = get_close_matches(inc['name'], prods_df['name'].tolist(), n=1, cutoff=0.3)
        if matches: best_match = matches[0]

    st.subheader("Assign Listing")
    target_prod = st.selectbox(
        "Product Folder", 
        ["(Create New Product)"] + list(prod_map.keys()),
        index=list(prod_map.keys()).index(best_match) + 1 if best_match else 0
    )
    
    if target_prod == "(Create New Product)":
        col1, col2 = st.columns(2)
        prod_name = col1.text_input("Master Name", value=inc['name'])
        prod_img = col1.text_input("Image URL (Paste clean link if overlay appeared)", value=inc['img'])
        if prod_img: st.image(prod_img, width=200, caption="Image Preview")
        
        prod_desc = col2.text_area("Description")
        cats = pd.read_sql_query("SELECT * FROM categories", conn)
        cat_map = dict(zip(cats['name'], cats['id']))
        cat_id = cat_map.get(col2.selectbox("Category", options=list(cat_map.keys())))
    else:
        p_info = prods_df[prods_df['id'] == prod_map[target_prod]].iloc[0]
        prod_name, cat_id, prod_img = p_info['name'], p_info['category_id'], p_info['image_url']
        st.info(f"Adding listing to existing: **{prod_name}**")
        if prod_img: st.image(prod_img, width=150)

    st.divider()
    
    detected_store = "Lazada" if "lazada" in inc['url'].lower() else "Shopee" if "shopee" in inc['url'].lower() else "Shop"
    c_a, c_b, c_c = st.columns([1, 2, 1])
    store = c_a.text_input("Store", value=detected_store)
    link = c_b.text_input("URL", value=inc['url'])
    price = c_c.number_input("Price", value=clean_p)
    
    if st.button("🚀 Save Listing"):
        today = datetime.now().strftime("%Y-%m-%d")
        c = conn.cursor()
        if target_prod == "(Create New Product)":
            c.execute("INSERT INTO products (name, description, image_url, category_id) VALUES (?, ?, ?, ?)", 
                      (prod_name, prod_desc, prod_img, cat_id))
            p_id = c.lastrowid
        else:
            p_id = prod_map[target_prod]
            
        existing = pd.read_sql_query(f"SELECT id FROM listings WHERE product_id={p_id} AND shop_name='{store}'", conn)
        if not existing.empty:
            c.execute("UPDATE listings SET price=?, url=?, last_updated=? WHERE id=?", (price, link, today, existing.iloc[0]['id']))
        else:
            c.execute("INSERT INTO listings (product_id, shop_name, price, url, last_updated) VALUES (?,?,?,?,?)", (p_id, store, price, link, today))
        
        conn.commit()
        st.success("Successfully Saved!")
        st.query_params.clear()

# --- TAB 1: DASHBOARD ---
with tab1:
    search = st.text_input("🔍 Search Items...")
    query = "SELECT p.*, c.name as cat_name FROM products p LEFT JOIN categories c ON p.category_id = c.id"
    if search: query += f" WHERE p.name LIKE '%{search}%'"
    
    display_df = pd.read_sql_query(query, conn)
    
    cols = st.columns(3)
    for i, prod in display_df.iterrows():
        with cols[i % 3]:
            with st.container(border=True):
                if prod['image_url']:
                    st.image(prod['image_url'], use_container_width=True)
                
                st.subheader(prod['name'])
                st.caption(f"📁 {prod['cat_name']}")
                
                list_df = pd.read_sql_query(f"SELECT * FROM listings WHERE product_id={prod['id']} ORDER BY price ASC", conn)
                if not list_df.empty:
                    st.metric("Best Price", f"₱{list_df.iloc[0]['price']:,.2f}")
                    st.divider()
                    for _, lst in list_df.iterrows():
                        st.write(f"**{lst['shop_name']}**: ₱{lst['price']:,.2f}")
                        st.link_button(f"Go to {lst['shop_name']}", lst['url'], use_container_width=True)
                
                if st.button("🗑️ Delete Product", key=f"del_{prod['id']}"):
                    conn.execute(f"DELETE FROM products WHERE id={prod['id']}")
                    conn.execute(f"DELETE FROM listings WHERE product_id={prod['id']}")
                    conn.commit()
                    st.rerun()
