import streamlit as st
import sqlite3
import pandas as pd
import re
from datetime import datetime
from difflib import get_close_matches

# --- 1. DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('price_monitor_v8.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT UNIQUE)')
    # Added "is_bought" column
    c.execute('''CREATE TABLE IF NOT EXISTS products 
                 (id INTEGER PRIMARY KEY, name TEXT, description TEXT, 
                  category_id INTEGER, is_bought INTEGER DEFAULT 0)''')
    # Listings table remains for current prices
    c.execute('''CREATE TABLE IF NOT EXISTS listings 
                 (id INTEGER PRIMARY KEY, product_id INTEGER, shop_name TEXT, 
                  price REAL, url TEXT, last_updated TEXT)''')
    # NEW: History table for the Graph
    c.execute('''CREATE TABLE IF NOT EXISTS history 
                 (id INTEGER PRIMARY KEY, product_id INTEGER, shop_name TEXT, 
                  price REAL, date TEXT)''')
    conn.commit()
    return conn

def get_incoming_data():
    params = st.query_params
    return {"name": params.get("name", ""), "url": params.get("url", ""), "price": params.get("price", "0")}

# --- 2. UI CONFIG ---
st.set_page_config(page_title="PricePro Buyer", layout="wide")
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
        prod_desc = col1.text_area("Notes")
        cats = pd.read_sql_query("SELECT * FROM categories", conn)
        cat_map = dict(zip(cats['name'], cats['id']))
        cat_id = cat_map.get(col2.selectbox("Category", options=list(cat_map.keys()) if not cats.empty else ["Add Category First"]))
    else:
        p_info = prods_df[prods_df['id'] == prod_map[target_prod]].iloc[0]
        prod_name, cat_id = p_info['name'], p_info['category_id']

    st.divider()
    c_a, c_b, c_c = st.columns([1, 2, 1])
    store = c_a.text_input("Store Name", value="Lazada" if "lazada" in inc['url'].lower() else "Shopee" if "shopee" in inc['url'].lower() else "Shop")
    link = c_b.text_input("URL", value=inc['url'])
    price = c_c.number_input("Price", value=clean_p)
    
    if st.button("🚀 Save and Log Price"):
        today = datetime.now().strftime("%Y-%m-%d")
        c = conn.cursor()
        if target_prod == "(Create New Product)":
            c.execute("INSERT INTO products (name, description, category_id) VALUES (?, ?, ?)", (prod_name, prod_desc, cat_id))
            p_id = c.lastrowid
        else:
            p_id = prod_map[target_prod]
            
        # Update current listing
        c.execute("INSERT OR REPLACE INTO listings (product_id, shop_name, price, url, last_updated) VALUES (?,?,?,?,?)", (p_id, store, price, link, today))
        # Log to history for the graph
        c.execute("INSERT INTO history (product_id, shop_name, price, date) VALUES (?,?,?,?)", (p_id, store, price, today))
        
        conn.commit()
        st.success("Price Logged!")
        st.query_params.clear()

# --- TAB 1: DASHBOARD ---
with tab1:
    col_s1, col_s2 = st.columns([2,1])
    search = col_s1.text_input("🔍 Search Active Items...")
    show_bought = col_s2.checkbox("Show Bought Items")
    
    status_filter = 1 if show_bought else 0
    query = f"SELECT p.*, c.name as cat_name FROM products p LEFT JOIN categories c ON p.category_id = c.id WHERE p.is_bought={status_filter}"
    if search: query += f" AND p.name LIKE '%{search}%'"
    
    display_df = pd.read_sql_query(query, conn)
    
    for i, prod in display_df.iterrows():
        with st.container(border=True):
            h1, h2, h3 = st.columns([4, 1, 1])
            h1.subheader(f"{'✅ ' if show_bought else ''}{prod['name']}")
            h1.caption(f"{prod['cat_name']} | {prod['description']}")
            
            if not show_bought:
                if h2.button("✔️ Mark Bought", key=f"buy_{prod['id']}"):
                    conn.execute(f"UPDATE products SET is_bought=1 WHERE id={prod['id']}")
                    conn.commit()
                    st.rerun()
            
            if h3.button("🗑️ Delete", key=f"del_{prod['id']}"):
                conn.execute(f"DELETE FROM products WHERE id={prod['id']}")
                conn.execute(f"DELETE FROM listings WHERE product_id={prod['id']}")
                conn.execute(f"DELETE FROM history WHERE product_id={prod['id']}")
                conn.commit()
                st.rerun()
            
            # List current prices
            l_df = pd.read_sql_query(f"SELECT * FROM listings WHERE product_id={prod['id']} ORDER BY price ASC", conn)
            if not l_df.empty:
                # Calculate Price Difference
                best_p = l_df.iloc[0]['price']
                worst_p = l_df.iloc[-1]['price']
                diff = worst_p - best_p
                
                if diff > 0:
                    st.info(f"💡 You save **₱{diff:,.2f}** by picking the cheapest store.")
                
                for _, lst in l_df.iterrows():
                    l1, l2, l3, l4 = st.columns([2, 1, 2, 1])
                    l1.write(f"🏪 {lst['shop_name']}")
                    l2.write(f"₱{lst['price']:,.2f}")
                    l3.write(f"📅 {lst['last_updated']}")
                    l4.link_button("Link", lst['url'])

                # --- THE GRAPH ---
                st.write("**Price History Over Time**")
                h_df = pd.read_sql_query(f"SELECT date, price, shop_name FROM history WHERE product_id={prod['id']} ORDER BY date ASC", conn)
                if not h_df.empty:
                    # Pivoting data for the line chart
                    chart_data = h_df.pivot_table(index='date', columns='shop_name', values='price')
                    st.line_chart(chart_data)
