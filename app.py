import streamlit as st
import sqlite3
import pandas as pd
import re
from datetime import datetime
from difflib import get_close_matches

# --- 1. DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('price_monitor_v11.db', check_same_thread=False)
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
    conn.commit()
    return conn

conn = init_db()
st.set_page_config(page_title="PricePro v11", layout="wide")

# --- 2. DATA INGESTION ---
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
        target_val = col1.number_input("Target Price (Buy goal)", value=0.0)
        prod_desc = col2.text_area("Notes")
        cats = pd.read_sql_query("SELECT * FROM categories", conn)
        cat_selection = col2.selectbox("Category", options=cats['name'].tolist() if not cats.empty else ["None"])
        cat_id = pd.read_sql_query(f"SELECT id FROM categories WHERE name='{cat_selection}'", conn).iloc[0][0] if not cats.empty else None
    else:
        p_info = prods_df[prods_df['id'] == prod_map[target_prod]].iloc[0]
        prod_name, target_val = p_info['name'], p_info['target_price']

    st.divider()
    ca, cb, cc = st.columns([1, 2, 1])
    store = ca.text_input("Store Name", value="Lazada" if "lazada" in inc['url'].lower() else "Shopee" if "shopee" in inc['url'].lower() else "Shop")
    link = cb.text_input("URL", value=inc['url'])
    try: p_val = float(re.sub(r'[^\d.]', '', inc['price'].replace(',','')))
    except: p_val = 0.0
    price = cc.number_input("Current Price", value=p_val)
    
    if st.button("🚀 Save and Update"):
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
    # 1. SUMMARY STATS (Updated for Voucher Savings)
    active_summary = pd.read_sql_query("""
        SELECT MIN(l.price) as best, MAX(l.price) as worst 
        FROM listings l JOIN products p ON l.product_id = p.id 
        WHERE p.is_bought=0 GROUP BY p.id""", conn)
    
    # Calculate voucher savings: (Lowest Listed Price at time of buy - Final Paid)
    bought_query = """
        SELECT p.id, p.final_paid, p.shipping_fee, MIN(l.price) as last_best_list
        FROM products p 
        LEFT JOIN listings l ON p.id = l.product_id
        WHERE p.is_bought=1 GROUP BY p.id
    """
    bought_df = pd.read_sql_query(bought_query, conn)
    
    total_spent = (bought_df['final_paid'] + bought_df['shipping_fee']).sum()
    voucher_savings = (bought_df['last_best_list'] - bought_df['final_paid']).sum()

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Watchlist Value", f"₱{active_summary['best'].sum():,.2f}")
    s2.metric("Market Savings", f"₱{(active_summary['worst'] - active_summary['best']).sum():,.2f}", help="Savings from choosing the cheapest store")
    s3.metric("Total Spent", f"₱{total_spent:,.2f}")
    s4.metric("Voucher Savings", f"₱{max(0, voucher_savings):,.2f}", help="Savings from vouchers/promos vs. lowest store price")
    st.divider()

    # 2. PRODUCT LIST
    search = st.text_input("🔍 Search Items...")
    show_bought = st.checkbox("Show Purchased Archive")
    
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
                with h2.popover("✔️ Bought"):
                    st.write("🎉 Checkout Details")
                    f_price = st.number_input("Final Price (with Vouchers)", value=0.0, key=f"fp_{prod['id']}")
                    f_ship = st.number_input("Shipping Fee", value=0.0, key=f"fs_{prod['id']}")
                    if st.button("Confirm", key=f"conf_{prod['id']}"):
                        conn.execute("UPDATE products SET is_bought=1, final_paid=?, shipping_fee=? WHERE id=?", 
                                     (f_price, f_ship, prod['id']))
                        conn.commit()
                        st.rerun()
            
            if h3.button("🗑️ Del", key=f"d_{prod['id']}"):
                conn.execute(f"DELETE FROM products WHERE id={prod['id']}"); conn.commit(); st.rerun()
            
            if show_bought:
                v_saved = prod['target_price'] - prod['final_paid'] if prod['target_price'] > 0 else 0
                st.write(f"💸 **Paid:** ₱{prod['final_paid']:,.2f} | **Ship:** ₱{prod['shipping_fee']:,.2f}")

            l_df = pd.read_sql_query(f"SELECT * FROM listings WHERE product_id={prod['id']} ORDER BY price ASC", conn)
            if not l_df.empty:
                best_price = l_df.iloc[0]['price']
                if not show_bought and prod['target_price'] > 0 and best_price <= prod['target_price']:
                    st.success(f"🎯 TARGET MET: Current Price ₱{best_price:,.2f} is under your ₱{prod['target_price']:,.2f} goal!")

                st.dataframe(l_df[['shop_name', 'price', 'last_updated']], hide_index=True, use_container_width=True)
                
                h_df = pd.read_sql_query(f"SELECT date, price, shop_name FROM history WHERE product_id={prod['id']} ORDER BY date ASC", conn)
                if len(h_df) > 1:
                    st.line_chart(h_df.pivot_table(index='date', columns='shop_name', values='price'))
