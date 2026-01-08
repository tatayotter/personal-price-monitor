import streamlit as st
import sqlite3
import pandas as pd
import re
from datetime import datetime
from difflib import get_close_matches

# --- 1. DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('price_monitor_v14.db', check_same_thread=False)
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
    
    # Prepopulate Categories
    default_cats = ["Tech & Gadgets", "Home & Living", "Health & Beauty", "Groceries", "Fashion"]
    for cat in default_cats:
        c.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat,))
    conn.commit()
    return conn

conn = init_db()
st.set_page_config(page_title="PricePro v14", layout="wide")

# --- 2. DATA INGESTION ---
inc = {"name": st.query_params.get("name", ""), "url": st.query_params.get("url", ""), "price": st.query_params.get("price", "0")}

tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "➕ Add/Update Listing", "📁 Categories"])

# --- TAB 3: CATEGORIES ---
with tab3:
    st.subheader("Manage Categories")
    c_add1, c_add2 = st.columns([3, 1])
    new_cat = c_add1.text_input("New Category Name")
    if c_add2.button("➕ Add", use_container_width=True) and new_cat:
        conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (new_cat,))
        conn.commit(); st.rerun()
    
    st.divider()
    cats_df = pd.read_sql_query("SELECT * FROM categories", conn)
    for _, row in cats_df.iterrows():
        c_col1, c_col2 = st.columns([3, 1])
        c_col1.write(f"📁 {row['name']}")
        if c_col2.button("🗑️ Remove", key=f"cat_del_{row['id']}", use_container_width=True):
            usage = pd.read_sql_query(f"SELECT id FROM products WHERE category_id={row['id']}", conn)
            if not usage.empty: st.error("Category in use!")
            else: conn.execute(f"DELETE FROM categories WHERE id={row['id']}"); conn.commit(); st.rerun()

# --- TAB 2: ADD/UPDATE ---
with tab2:
    prods_df = pd.read_sql_query("SELECT * FROM products WHERE is_bought=0", conn)
    prod_map = dict(zip(prods_df['name'], prods_df['id']))
    best_match = get_close_matches(inc['name'], list(prod_map.keys()), n=1, cutoff=0.2)[0] if inc['name'] and prod_map else None

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
        else: p_id = prod_map[target_prod]
        c.execute("INSERT OR REPLACE INTO listings (product_id, shop_name, price, url, last_updated) VALUES (?,?,?,?,?)", (p_id, store, price, link, today))
        c.execute("INSERT INTO history (product_id, shop_name, price, date) VALUES (?,?,?,?)", (p_id, store, price, today))
        conn.commit(); st.success("Updated!"); st.query_params.clear()

# --- TAB 1: DASHBOARD ---
with tab1:
    bought_df = pd.read_sql_query("SELECT final_paid, shipping_fee, (SELECT MIN(price) FROM listings WHERE product_id=products.id) as last_list FROM products WHERE is_bought=1", conn)
    total_spent = (bought_df['final_paid'] + bought_df['shipping_fee']).sum()
    voucher_savings = (bought_df['last_list'] - bought_df['final_paid']).sum()

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Spent (Total)", f"₱{total_spent:,.2f}")
    s4.metric("Voucher Savings", f"₱{max(0, voucher_savings):,.2f}")
    st.divider()

    search = st.text_input("🔍 Search...")
    show_bought = st.checkbox("Show Purchased Archive")
    prods = pd.read_sql_query(f"SELECT p.*, c.name as cat_name FROM products p LEFT JOIN categories c ON p.category_id = c.id WHERE p.is_bought={1 if show_bought else 0} AND p.name LIKE '%{search}%'", conn)
    
    for _, prod in prods.iterrows():
        with st.container(border=True):
            h1, h2, h3 = st.columns([4, 1, 1])
            h1.subheader(f"{'✅ ' if show_bought else ''}{prod['name']}")
            h1.caption(f"{prod['cat_name']} | {prod['description']}")
            
            if not show_bought:
                with h2.popover("✔️ Bought"):
                    f_price = st.number_input("Final Paid", value=0.0, key=f"fp_{prod['id']}")
                    f_ship = st.number_input("Shipping", value=0.0, key=f"fs_{prod['id']}")
                    if st.button("Confirm", key=f"conf_{prod['id']}"):
                        conn.execute("UPDATE products SET is_bought=1, final_paid=?, shipping_fee=? WHERE id=?", (f_price, f_ship, prod['id'])); conn.commit(); st.rerun()
            
            if h3.button("🗑️ Del", key=f"d_{prod['id']}"):
                conn.execute(f"DELETE FROM products WHERE id={prod['id']}"); conn.commit(); st.rerun()

            l_df = pd.read_sql_query(f"SELECT * FROM listings WHERE product_id={prod['id']} ORDER BY price ASC", conn)
            if not l_df.empty:
                # Add "Stale" emoji to date column
                def check_stale(date_str):
                    days = (datetime.now() - datetime.strptime(date_str, "%Y-%m-%d")).days
                    return f"🔴 {date_str} ({days}d ago)" if days > 7 else f"🟢 {date_str}"

                l_df['last_updated'] = l_df['last_updated'].apply(check_stale)

                if not show_bought:
                    best_p = l_df.iloc[0]['price']
                    if prod['target_price'] > 0 and best_p <= prod['target_price']:
                        st.success(f"🎯 TARGET MET: ₱{best_p:,.2f}")

                st.dataframe(
                    l_df[['shop_name', 'price', 'url', 'last_updated']], 
                    column_config={
                        "url": st.column_config.LinkColumn("Shop Link", display_text="Visit Store"),
                        "last_updated": st.column_config.TextColumn("Last Checked")
                    },
                    hide_index=True, use_container_width=True
                )
