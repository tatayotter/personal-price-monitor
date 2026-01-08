import streamlit as st
import sqlite3
import pandas as pd
import re
from datetime import datetime
from difflib import get_close_matches

# --- 1. DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('price_monitor_v9.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT UNIQUE)')
    c.execute('''CREATE TABLE IF NOT EXISTS products 
                 (id INTEGER PRIMARY KEY, name TEXT, description TEXT, 
                  category_id INTEGER, target_price REAL DEFAULT 0, is_bought INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS listings 
                 (id INTEGER PRIMARY KEY, product_id INTEGER, shop_name TEXT, 
                  price REAL, url TEXT, last_updated TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS history 
                 (id INTEGER PRIMARY KEY, product_id INTEGER, shop_name TEXT, 
                  price REAL, date TEXT)''')
    conn.commit()
    return conn

# --- 2. LOGIC ---
conn = init_db()
st.set_page_config(page_title="PricePro Personal", layout="wide")

inc = {
    "name": st.query_params.get("name", ""),
    "url": st.query_params.get("url", ""),
    "price": st.query_params.get("price", "0")
}

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
    prods_df = pd.read_sql_query("SELECT * FROM products WHERE is_bought=0", conn)
    prod_map = dict(zip(prods_df['name'], prods_df['id']))
    
    best_match = None
    if inc['name'] and not prods_df.empty:
        matches = get_close_matches(inc['name'], prods_df['name'].tolist(), n=1, cutoff=0.2)
        if matches: best_match = matches[0]

    st.subheader("Assign Listing")
    target_prod = st.selectbox("Product Folder", ["(Create New Product)"] + list(prod_map.keys()),
                                index=list(prod_map.keys()).index(best_match) + 1 if best_match else 0)
    
    if target_prod == "(Create New Product)":
        col1, col2 = st.columns(2)
        prod_name = col1.text_input("Master Product Name", value=inc['name'])
        target_val = col1.number_input("Target Price (Buy when it hits this)", value=0.0)
        prod_desc = col2.text_area("Notes")
        cats = pd.read_sql_query("SELECT * FROM categories", conn)
        cat_id = pd.read_sql_query(f"SELECT id FROM categories WHERE name='{col2.selectbox('Category', options=cats['name'].tolist() if not cats.empty else ['None'])}'", conn).iloc[0][0] if not cats.empty else None
    else:
        p_info = prods_df[prods_df['id'] == prod_map[target_prod]].iloc[0]
        prod_name = p_info['name']
        target_val = p_info['target_price']

    st.divider()
    ca, cb, cc = st.columns([1, 2, 1])
    store = ca.text_input("Store Name", value="Lazada" if "lazada" in inc['url'].lower() else "Shopee" if "shopee" in inc['url'].lower() else "Shop")
    link = cb.text_input("URL", value=inc['url'])
    # Parse incoming price string safely
    try: p_val = float(re.sub(r'[^\d.]', '', inc['price'].replace(',','')))
    except: p_val = 0.0
    price = cc.number_input("Current Price", value=p_val)
    
    if st.button("🚀 Save and Update Dashboard"):
        today = datetime.now().strftime("%Y-%m-%d")
        c = conn.cursor()
        if target_prod == "(Create New Product)":
            c.execute("INSERT INTO products (name, description, category_id, target_price) VALUES (?, ?, ?, ?)", (prod_name, prod_desc, cat_id, target_val))
            p_id = c.lastrowid
        else:
            p_id = prod_map[target_prod]
            
        c.execute("INSERT OR REPLACE INTO listings (product_id, shop_name, price, url, last_updated) VALUES (?,?,?,?,?)", (p_id, store, price, link, today))
        c.execute("INSERT INTO history (product_id, shop_name, price, date) VALUES (?,?,?,?)", (p_id, store, price, today))
        conn.commit()
        st.success("Updated!")

# --- TAB 1: DASHBOARD ---
with tab1:
    # 1. SUMMARY STATS
    all_active = pd.read_sql_query("""
        SELECT MIN(l.price) as best, MAX(l.price) as worst 
        FROM listings l JOIN products p ON l.product_id = p.id 
        WHERE p.is_bought=0 GROUP BY p.id""", conn)
    
    bought_data = pd.read_sql_query("SELECT MIN(price) as spent FROM listings JOIN products ON listings.product_id = products.id WHERE products.is_bought=1 GROUP BY products.id", conn)

    s1, s2, s3 = st.columns(3)
    s1.metric("Total Watchlist Value", f"₱{all_active['best'].sum():,.2f}")
    s2.metric("Money Saved (vs Max)", f"₱{(all_active['worst'] - all_active['best']).sum():,.2f}")
    s3.metric("Total Already Spent", f"₱{bought_data['spent'].sum():,.2f}")
    st.divider()

    # 2. PRODUCT LIST
    search = st.text_input("🔍 Search Active Items...")
    show_bought = st.checkbox("Show Purchased History")
    
    status = 1 if show_bought else 0
    query = f"SELECT p.*, c.name as cat_name FROM products p LEFT JOIN categories c ON p.category_id = c.id WHERE p.is_bought={status}"
    if search: query += f" AND p.name LIKE '%{search}%'"
    
    prods = pd.read_sql_query(query, conn)
    
    for _, prod in prods.iterrows():
        with st.container(border=True):
            h1, h2, h3 = st.columns([4, 1, 1])
            h1.subheader(f"{'✅ ' if show_bought else ''}{prod['name']}")
            h1.caption(f"{prod['cat_name']} | {prod['description']}")
            
            if not show_bought:
                if h2.button("✔️ Bought", key=f"b_{prod['id']}"):
                    conn.execute(f"UPDATE products SET is_bought=1 WHERE id={prod['id']}"); conn.commit(); st.rerun()
            
            if h3.button("🗑️ Del", key=f"d_{prod['id']}"):
                conn.execute(f"DELETE FROM products WHERE id={prod['id']}"); conn.commit(); st.rerun()
            
            l_df = pd.read_sql_query(f"SELECT * FROM listings WHERE product_id={prod['id']} ORDER BY price ASC", conn)
            if not l_df.empty:
                # Target Price Logic
                best = l_df.iloc[0]['price']
                if prod['target_price'] > 0 and best <= prod['target_price']:
                    st.success(f"🎯 TARGET MET: Price is below your ₱{prod['target_price']:,.2f} goal!")

                # Listings and Graph
                st.dataframe(l_df[['shop_name', 'price', 'last_updated']], hide_index=True, use_container_width=True)
                
                h_df = pd.read_sql_query(f"SELECT date, price, shop_name FROM history WHERE product_id={prod['id']} ORDER BY date ASC", conn)
                if len(h_df) > 1:
                    st.line_chart(h_df.pivot_table(index='date', columns='shop_name', values='price'))
