import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
import time

# --- 1. DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('monitor.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT UNIQUE)')
    c.execute('''CREATE TABLE IF NOT EXISTS items 
                 (id INTEGER PRIMARY KEY, name TEXT, url TEXT, image_url TEXT, 
                  status TEXT, category_id INTEGER,
                  FOREIGN KEY(category_id) REFERENCES categories(id))''')
    c.execute('CREATE TABLE IF NOT EXISTS prices (item_id INTEGER, price REAL, date TEXT)')
    conn.commit()
    return conn

# --- 2. SCRAPER ENGINE ---
def scrape_data(url):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    result = {"price": 0.0, "image": "https://via.placeholder.com/150"}
    try:
        driver.get(url)
        time.sleep(5)
        # Price Scraper (Lazada/Shopee common classes)
        price_el = driver.find_element(By.CSS_SELECTOR, ".pdp-price, ._3e_ne, [data-testid='price']")
        result["price"] = float(''.join(filter(str.isdigit, price_el.text)))
        
        # Image Scraper
        img_el = driver.find_element(By.CSS_SELECTOR, ".pdp-mod-common-gallery-viewer img, .gallery-preview-panel img")
        result["image"] = img_el.get_attribute("src")
    except:
        pass
    finally:
        driver.quit()
    return result

# --- 3. WEB INTERFACE ---
st.set_page_config(page_title="PricePro PH", layout="wide")
conn = init_db()

# Sidebar Budget Summary
st.sidebar.title("💰 Budget Summary")
summary_query = """
    SELECT c.name, SUM(p.price) as total FROM items i 
    JOIN categories c ON i.category_id = c.id 
    JOIN prices p ON p.item_id = i.id
    WHERE i.status = 'Watching' AND p.date = (SELECT MAX(date) FROM prices WHERE item_id = i.id)
    GROUP BY c.name
"""
summary_df = pd.read_sql_query(summary_query, conn)
for _, row in summary_df.iterrows():
    st.sidebar.metric(row['name'], f"₱{row['total']:,.2f}")

tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "➕ Add Item", "📁 Categories"])

with tab3:
    st.subheader("Manage Categories")
    new_cat = st.text_input("Category Name (e.g. 💻 PC Parts)")
    if st.button("Add Category"):
        conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (new_cat,))
        conn.commit()
        st.success("Category added!")

with tab2:
    st.subheader("Track New Product")
    cats = pd.read_sql_query("SELECT * FROM categories", conn)
    cat_dict = dict(zip(cats['name'], cats['id']))
    
    with st.form("add_form"):
        name = st.text_input("Item Name")
        url = st.text_input("URL")
        category = st.selectbox("Category", options=list(cat_dict.keys()))
        if st.form_submit_button("Start Tracking"):
            with st.spinner("Scraping product info..."):
                data = scrape_data(url)
                c = conn.cursor()
                c.execute("INSERT INTO items (name, url, image_url, status, category_id) VALUES (?,?,?,?,?)",
                          (name, url, data['image'], 'Watching', cat_dict[category]))
                c.execute("INSERT INTO prices (item_id, price, date) VALUES (?,?,?)",
                          (c.lastrowid, data['price'], datetime.now().strftime("%Y-%m-%d")))
                conn.commit()
                st.success("Added to Dashboard!")

with tab1:
    items = pd.read_sql_query("SELECT i.*, c.name as cat_name FROM items i JOIN categories c ON i.category_id = c.id WHERE status='Watching'", conn)
    
    if items.empty:
        st.info("Your dashboard is empty. Add an item to get started!")
    else:
        cols = st.columns(3)
        for i, item in items.iterrows():
            with cols[i % 3]:
                with st.container(border=True):
                    st.image(item['image_url'], use_container_width=True)
                    st.subheader(item['name'])
                    st.caption(f"📁 {item['cat_name']}")
                    
                    p_history = pd.read_sql_query(f"SELECT price, date FROM prices WHERE item_id={item['id']} ORDER BY date DESC", conn)
                    if not p_history.empty:
                        st.metric("Price", f"₱{p_history.iloc[0]['price']:,.2f}")
                        st.line_chart(p_history.set_index('date'), height=150)
                    
                    if st.button("Mark as Bought", key=f"b_{item['id']}"):
                        conn.execute(f"UPDATE items SET status='Bought' WHERE id={item['id']}")
                        conn.commit()
                        st.rerun()
