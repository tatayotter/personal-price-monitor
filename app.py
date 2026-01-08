import streamlit as st
import sqlite3
import pandas as pd
import re
from datetime import datetime

# --- 1. DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('price_monitor.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT UNIQUE)')
    c.execute('''CREATE TABLE IF NOT EXISTS products 
                 (id INTEGER PRIMARY KEY, name TEXT, description TEXT, category_id INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS listings 
                 (id INTEGER PRIMARY KEY, product_id INTEGER, shop_name TEXT, 
                  price REAL, url TEXT, last_updated TEXT)''')
    conn.commit()
    return conn

def parse_price(raw_text):
    # Regex sniffs for currency patterns like ₱1,234 or $50
    price_match = re.search(r"(?:₱|\$|PHP|USD)\s?([\d,]+\.?\d*)", raw_text)
    if price_match:
        # Removes commas and converts to a decimal number
        return float(price_match.group(1).replace(',', ''))
    return 0.0

# --- 2. UI CONFIG ---
st.set_page_config(page_title="PricePro Dashboard", layout="wide")
conn = init_db()

# --- 3. TABS ---
tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "➕ Add/Update Listing", "📁 Categories"])

# --- TAB 3: CATEGORIES ---
with tab3:
    st.subheader("Manage Categories")
    col_cat1, col_cat2 = st.columns([2, 1])
    with col_cat1:
        new_cat = st.text_input("Category Name", placeholder="e.g. 🏠 Home, 💻 Tech")
    with col_cat2:
        if st.button("Add Category") and new_cat:
            conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (new_cat,))
            conn.commit()
            st.rerun()

# --- TAB 2: ADD/UPDATE ---
with tab2:
    st.subheader("⚡ Quick Add or Price Refresh")
    
    prods_df = pd.read_sql_query("SELECT * FROM products", conn)
    prod_map = dict(zip(prods_df['name'], prods_df['id']))
    
    target_prod = st.selectbox("Assign to Product", ["(Create New Product)"] + list(prod_map.keys()))
    
    if target_prod == "(Create New Product)":
        col1, col2 = st.columns(2)
        prod_name = col1.text_input("New Product Name")
        prod_desc = col1.text_area("Short Description", placeholder="e.g. 256GB, Color: Black")
        
        cats = pd.read_sql_query("SELECT * FROM categories", conn)
        cat_map = dict(zip(cats['name'], cats['id']))
        prod_cat = col2.selectbox("Category", options=list(cat_map.keys()))
        cat_id = cat_map.get(prod_cat)
    else:
        p_info = prods_df[prods_df['id'] == prod_map[target_prod]].iloc[0]
        st.info(f"Updating: **{p_info['name']}**")
        prod_name = p_info['name']
        cat_id = p_info['category_id']

    st.divider()
    
    col_a, col_b = st.columns(2)
    store = col_a.text_input("Store/Shop Name (e.g. Lazada, Shopee)")
    link = col_b.text_input("Product URL (The link to the shop)")
    
    paste_area = st.text_area("Paste Content from Shop Page (Ctrl+A -> Ctrl+C -> Ctrl+V)", height=150)
    
    if st.button("🚀 Save to Dashboard"):
        final_price = parse_price(paste_area)
        today = datetime.now().strftime("%Y-%m-%d")
        c = conn.cursor()
        
        if target_prod == "(Create New Product)":
            c.execute("INSERT INTO products (name, description, category_id) VALUES (?, ?, ?)", 
                      (prod_name, prod_desc, cat_id))
            p_id = c.lastrowid
        else:
            p_id = prod_map[target_prod]
            
        existing = pd.read_sql_query(f"SELECT id FROM listings WHERE product_id={p_id} AND shop_name='{store}'", conn)
        
        if not existing.empty:
            c.execute("UPDATE listings SET price=?, url=?, last_updated=? WHERE id=?", 
                      (final_price, link, today, existing.iloc[0]['id']))
        else:
            c.execute("INSERT INTO listings (product_id, shop_name, price, url, last_updated) VALUES (?,?,?,?,?)",
                      (p_id, store, final_price, link, today))
        
        conn.commit()
        st.success(f"Successfully saved ₱{final_price:,.2f} for {store}!")

# --- TAB 1: DASHBOARD ---
with tab1:
    col_search1, col_search2 = st.columns([2, 1])
    search_query = col_search1.text_input("🔍 Search Products...", "")
    
    all_cats = pd.read_sql_query("SELECT * FROM categories", conn)
    filter_cat = col_search2.selectbox("Filter by Category", ["All"] + list(all_cats['name']))
    
    query = """
        SELECT p.*, c.name as cat_name FROM products p 
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE 1=1
    """
    if search_query:
        query += f" AND p.name LIKE '%{search_query}%'"
    if filter_cat != "All":
        query += f" AND c.name = '{filter_cat}'"
        
    display_prods = pd.read_sql_query(query, conn)
    
    for _, prod in display_prods.iterrows():
        with st.container(border=True):
            t_col1, t_col2 = st.columns([3, 1])
            t_col1.subheader(f"{prod['name']}")
            t_col2.info(f"📁 {prod['cat_name']}")
            st.write(f"_{prod['description']}_")
            
            list_df = pd.read_sql_query(f"SELECT * FROM listings WHERE product_id={prod['id']} ORDER BY price ASC", conn)
            
            if not list_df.empty:
                st.write("---")
                for _, lst in list_df.iterrows():
                    l_c1, l_c2, l_c3, l_c4 = st.columns([2, 1, 2, 1])
                    l_c1.write(f"🏪 **{lst['shop_name']}**")
                    l_c2.write(f"₱{lst['price']:,.2f}")
                    
                    d_old = (datetime.now() - datetime.strptime(lst['last_updated'], "%Y-%m-%d")).days
                    color = "red" if d_old > 7 else "gray"
                    l_c3.markdown(f":{color}[📅 {lst['last_updated']} ({d_old}d ago)]")
                    
                    l_c4.link_button("🔗 Shop", lst['url'], use_container_width=True)
                
                st.success(f"🏆 Best Deal: ₱{list_df.iloc[0]['price']:,.2f} ({list_df.iloc[0]['shop_name']})")
