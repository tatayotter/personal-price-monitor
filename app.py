import streamlit as st
import sqlite3
import pandas as pd
import re
from datetime import datetime
from difflib import get_close_matches

# --- 1. DATABASE SETUP ---
@st.cache_resource
def get_connection():
    # Using a new DB version name to ensure schema updates apply
    conn = sqlite3.connect('price_monitor_v20.db', check_same_thread=False)
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT UNIQUE)')
    # Added image_url column to the products table
    c.execute('''CREATE TABLE IF NOT EXISTS products 
                 (id INTEGER PRIMARY KEY, name TEXT, description TEXT, 
                  category_id INTEGER, target_price REAL DEFAULT 0, 
                  is_bought INTEGER DEFAULT 0, final_paid REAL DEFAULT 0, 
                  shipping_fee REAL DEFAULT 0, image_url TEXT)''')
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

init_db()
conn = get_connection()

st.set_page_config(page_title="PricePro v20", layout="wide", page_icon="💰")

# --- 2. CAPTURE URL PARAMETERS ---
params = st.query_params
inc = {
    "name": params.get("name", ""),
    "url": params.get("url", ""),
    "price": params.get("price", "0"),
    "img": params.get("img", ""),
    "tab_req": params.get("tab", "dashboard")
}

# --- 3. SIDEBAR NAVIGATION ---
nav_index = 1 if inc['tab_req'] == 'add' else 0
st.sidebar.title("💰 PricePro")
page = st.sidebar.radio("Navigation", ["📊 Dashboard", "➕ Add/Update Listing", "📁 Categories"], index=nav_index)

# --- PAGE: CATEGORIES ---
if page == "📁 Categories":
    st.header("Manage Categories")
    c_add1, c_add2 = st.columns([3, 1])
    new_cat = c_add1.text_input("New Category Name")
    if c_add2.button("➕ Add", use_container_width=True) and new_cat:
        try:
            conn.execute("INSERT INTO categories (name) VALUES (?)", (new_cat,))
            conn.commit()
            st.rerun()
        except sqlite3.IntegrityError:
            st.error("Category already exists!")
    
    st.divider()
    cats_df = pd.read_sql_query("SELECT * FROM categories", conn)
    for _, row in cats_df.iterrows():
        c_col1, c_col2 = st.columns([3, 1])
        c_col1.write(f"📁 {row['name']}")
        if c_col2.button("🗑️ Remove", key=f"cat_del_{row['id']}", use_container_width=True):
            usage = pd.read_sql_query("SELECT id FROM products WHERE category_id=?", conn, params=(row['id'],))
            if not usage.empty: 
                st.error("Category in use!")
            else: 
                conn.execute("DELETE FROM categories WHERE id=?", (row['id'],))
                conn.commit()
                st.rerun()

# --- PAGE: ADD/UPDATE ---
elif page == "➕ Add/Update Listing":
    st.header("Add or Update Listing")

    if inc['img'] or inc['name']:
        with st.container(border=True):
            col_img, col_txt = st.columns([1, 4])
            if inc['img']:
                col_img.image(inc['img'], width=150)
            col_txt.markdown(f"**Incoming Product:**\n{inc['name']}")
            if inc['url']:
                col_txt.caption(f"Source: {inc['url']}")

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
        cat_id = cats[cats['name'] == cat_selection]['id'].values[0] if not cats.empty else None
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

    if st.button("🚀 Save Listing", disabled=(price <= 0), use_container_width=True):
        today = datetime.now().strftime("%Y-%m-%d")
        c = conn.cursor()
        if target_prod == "(Create New Product)":
            c.execute("INSERT INTO products (name, description, category_id, target_price, image_url) VALUES (?, ?, ?, ?, ?)", 
                      (prod_name, prod_desc, cat_id, target_val, inc['img']))
            p_id = c.lastrowid
        else: 
            p_id = prod_map[target_prod]
            # Update image if existing product doesn't have one
            c.execute("UPDATE products SET image_url = COALESCE(image_url, ?) WHERE id = ?", (inc['img'], p_id))
        
        c.execute("INSERT OR REPLACE INTO listings (product_id, shop_name, price, url, last_updated) VALUES (?,?,?,?,?)", (p_id, store, price, link, today))
        c.execute("INSERT INTO history (product_id, shop_name, price, date) VALUES (?,?,?,?)", (p_id, store, price, today))
        conn.commit()
        st.success(f"Successfully saved {prod_name}!")
        st.query_params.clear()
        st.rerun()

# --- PAGE: DASHBOARD ---
elif page == "📊 Dashboard":
    bought_df = pd.read_sql_query("SELECT final_paid, shipping_fee, (SELECT MIN(price) FROM listings WHERE product_id=products.id) as last_list FROM products WHERE is_bought=1", conn)
    total_spent = (bought_df['final_paid'] + bought_df['shipping_fee']).sum()
    v_savings = (bought_df['last_list'] - bought_df['final_paid']).sum()

    s1, s2, s3 = st.columns(3)
    s1.metric("Spent (Total)", f"₱{total_spent:,.2f}")
    s2.metric("Voucher Savings", f"₱{max(0, v_savings):,.2f}")
    st.divider()

    search = st.text_input("🔍 Search Dashboard...")
    show_bought = st.checkbox("Show Purchased Archive")
    
    status = 1 if show_bought else 0
    query = """SELECT p.*, c.name as cat_name 
               FROM products p 
               LEFT JOIN categories c ON p.category_id = c.id 
               WHERE p.is_bought=? AND p.name LIKE ?"""
    prods = pd.read_sql_query(query, conn, params=(status, f'%{search}%'))
    
    for _, prod in prods.iterrows():
        with st.container(border=True):
            # Layout: Image | Details | Actions
            col_img, col_main, col_btns = st.columns([1, 4, 1.2])
            
            with col_img:
                if prod['image_url']:
                    st.image(prod['image_url'], use_container_width=True)
                else:
                    st.markdown("🖼️\n*No Image*")

            with col_main:
                st.subheader(f"{'✅ ' if show_bought else ''}{prod['name']}")
                st.caption(f"{prod['cat_name']} | {prod['description']}")
                if prod['target_price'] > 0:
                    st.write(f"🎯 Target: **₱{prod['target_price']:,.2f}**")

            with col_btns:
                # Row of action buttons using popovers for cleanliness
                btn_edit, btn_bought, btn_del = st.columns(3)
                
                with btn_edit.popover("📝"):
                    new_name = st.text_input("Edit Name", value=prod['name'], key=f"ed_n_{prod['id']}")
                    if st.button("Save", key=f"s_n_{prod['id']}"):
                        conn.execute("UPDATE products SET name=? WHERE id=?", (new_name, prod['id']))
                        conn.commit()
                        st.rerun()

                if not show_bought:
                    with btn_bought.popover("✔️"):
                        f_p = st.number_input("Final Paid", value=0.0, key=f"fp_{prod['id']}")
                        f_s = st.number_input("Shipping", value=0.0, key=f"fs_{prod['id']}")
                        if st.button("Confirm", key=f"c_{prod['id']}"):
                            conn.execute("UPDATE products SET is_bought=1, final_paid=?, shipping_fee=? WHERE id=?", (f_p, f_s, prod['id']))
                            conn.commit()
                            st.rerun()
                
                if btn_del.button("🗑️", key=f"d_{prod['id']}"):
                    conn.execute("DELETE FROM products WHERE id=?", (prod['id'],))
                    conn.commit()
                    st.rerun()

            # --- Listings Table ---
            l_df = pd.read_sql_query("SELECT * FROM listings WHERE product_id=? ORDER BY price ASC", conn, params=(prod['id'],))
            if not l_df.empty:
                def check_stale(d):
                    try:
                        diff = (datetime.now() - datetime.strptime(d, "%Y-%m-%d")).days
                        return f"🔴 {d} ({diff}d ago)" if diff > 7 else f"🟢 {d}"
                    except: return d
                
                l_df['last_updated'] = l_df['last_updated'].apply(check_stale)
                
                st.dataframe(
                    l_df[['shop_name', 'price', 'url', 'last_updated']], 
                    column_config={"url": st.column_config.LinkColumn("Shop Link", display_text="Visit Store")},
                    hide_index=True, use_container_width=True
                )

                # --- History Chart ---
                h_df = pd.read_sql_query("SELECT date, price, shop_name FROM history WHERE product_id=? ORDER BY date ASC", conn, params=(prod['id'],))
                if len(h_df) > 1:
                    with st.expander("📈 View Price Trend"):
                        chart_data = h_df.pivot_table(index='date', columns='shop_name', values='price')
                        st.line_chart(chart_data)
