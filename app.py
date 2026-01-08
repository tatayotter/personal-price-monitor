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
    # Changed 'url' to 'urls' to store multiple links separated by commas
    c.execute('''CREATE TABLE IF NOT EXISTS items 
                 (id INTEGER PRIMARY KEY, name TEXT, urls TEXT, image_url TEXT, 
                  status TEXT, category_id INTEGER)''')
    c.execute('CREATE TABLE IF NOT EXISTS prices (item_id INTEGER, price REAL, source_url TEXT, date TEXT)')
    conn.commit()
    return conn

# --- 2. MULTI-LINK SCRAPER ---
def scrape_multi_prices(urls_string):
    options = Options()
    # These 5 lines are MANDATORY for Streamlit Cloud
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.binary_location = "/usr/bin/chromium-browser" # Points to the cloud's browser
    
    # Updated driver setup for the cloud environment
    service = Service("/usr/bin/chromedriver") 
    driver = webdriver.Chrome(service=service, options=options)
    
    urls = [url.strip() for url in urls_string.split(",")]
    results = []
    main_image = "https://via.placeholder.com/150"

    for url in urls:
        try:
            driver.get(url)
            time.sleep(5)
            # Standard price selector
            price_el = driver.find_element(By.CSS_SELECTOR, ".pdp-price, ._3e_ne, [data-testid='price']")
            price = float(''.join(filter(str.isdigit, price_el.text)))
            
            if main_image == "https://via.placeholder.com/150":
                try:
                    img_el = driver.find_element(By.CSS_SELECTOR, ".pdp-mod-common-gallery-viewer img, .gallery-preview-panel img")
                    main_image = img_el.get_attribute("src")
                except: pass
            
            results.append({"price": price, "url": url})
        except:
            continue
            
    driver.quit()
    return results, main_image

# --- 3. WEB INTERFACE ---
st.set_page_config(page_title="PricePro Multi-Compare", layout="wide")
conn = init_db()

tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "➕ Add Item", "📁 Categories"])

with tab2:
    st.subheader("Track Product (Add multiple links)")
    cats = pd.read_sql_query("SELECT * FROM categories", conn)
    cat_dict = dict(zip(cats['name'], cats['id']))
    
    with st.form("add_form"):
        name = st.text_input("Item Name")
        # Instructions for the user
        urls_input = st.text_area("Paste URLs (separate each with a comma)")
        category = st.selectbox("Category", options=list(cat_dict.keys()))
        
        if st.form_submit_button("Start Comparing"):
            with st.spinner("Visiting all stores... this takes a moment."):
                price_data, img_url = scrape_multi_prices(urls_input)
                
                if price_data:
                    # Find the cheapest price found
                    cheapest = min(price_data, key=lambda x: x['price'])
                    
                    c = conn.cursor()
                    c.execute("INSERT INTO items (name, urls, image_url, status, category_id) VALUES (?,?,?,?,?)",
                              (name, urls_input, img_url, 'Watching', cat_dict[category]))
                    item_id = c.lastrowid
                    c.execute("INSERT INTO prices (item_id, price, source_url, date) VALUES (?,?,?,?)",
                              (item_id, cheapest['price'], cheapest['url'], datetime.now().strftime("%Y-%m-%d")))
                    conn.commit()
                    st.success(f"Best Price Found: ₱{cheapest['price']:,.2f}")
                else:
                    st.error("Could not find prices on any of those links.")

with tab1:
    # (Dashboard logic remains similar, but st.metric now reflects the lowest price found)
    items = pd.read_sql_query("SELECT i.*, c.name as cat_name FROM items i JOIN categories c ON i.category_id = c.id WHERE status='Watching'", conn)
    cols = st.columns(3)
    for i, item in items.iterrows():
        with cols[i % 3]:
            with st.container(border=True):
                st.image(item['image_url'], use_container_width=True)
                st.subheader(item['name'])
                
                p_history = pd.read_sql_query(f"SELECT price, source_url FROM prices WHERE item_id={item['id']} ORDER BY date DESC LIMIT 1", conn)
                if not p_history.empty:
                    st.metric("Lowest Price", f"₱{p_history.iloc[0]['price']:,.2f}")
                    st.caption(f"Found at: {p_history.iloc[0]['source_url'][:30]}...")
