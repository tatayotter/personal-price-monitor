import streamlit as st
import sqlite3
import pandas as pd
import re
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By

# --- 1. DATABASE SYSTEM ---
def init_db():
    conn = sqlite3.connect('monitor.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT UNIQUE)')
    c.execute('''CREATE TABLE IF NOT EXISTS items 
                 (id INTEGER PRIMARY KEY, name TEXT, urls TEXT, image_url TEXT, 
                  status TEXT, category_id INTEGER)''')
    c.execute('CREATE TABLE IF NOT EXISTS prices (item_id INTEGER, price REAL, source_url TEXT, date TEXT)')
    conn.commit()
    return conn

# --- 2. SMART-FOCUS SCRAPER ---
def scrape_multi_prices(urls_string):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

    # Cloud-friendly driver initialization
    try:
        options.binary_location = "/usr/bin/chromium"
        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=options)
    except:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    urls = [url.strip() for url in urls_string.split(",") if url.strip()]
    results = []
    main_image = "https://via.placeholder.com/150"

    for url in urls:
        try:
            driver.get(url)
            time.sleep(8) # Allow JS to render prices
            
            # --- TARGETED PRICE EXTRACTION ---
            # Find all elements likely to hold prices
            elements = driver.find_elements(By.XPATH, "//*[self::span or self::div or self::p or self::h1 or self::h2]")
            potential_prices = []
            
            for el in elements:
                try:
                    text = el.text.strip()
                    # Regex for currency patterns like ₱1,200, $50, or 1,500.00 PHP
                    if re.search(r"(?:₱|\$|PHP|USD)\s?[\d,]+\.?\d*", text):
                        size = el.size['height'] * el.size['width']
                        y_pos = el.location['y']
                        
                        # Filter: Ignore headers (y < 200) and very small text
                        if y_pos > 200 and size > 0:
                            potential_prices.append({"text": text, "size": size})
                except: continue

            if potential_prices:
                # The biggest price in the middle of the page is the winner
                potential_prices.sort(key=lambda x: x['size'], reverse=True)
                raw_price = potential_prices[0]['text']
                # Extract only the digits and decimal
                clean_price = float(''.join(re.findall(r"[\d.]", raw_price.replace(',', ''))))
                results.append({"price": clean_price, "url": url})
            
            # --- SMART IMAGE EXTRACTION ---
            if main_image == "https://via.placeholder.com/150":
                images = driver.find_elements(By.TAG_NAME, "img")
                for img in images:
                    src = img.get_attribute("src")
                    if src and "http" in src and any(x in src.lower() for x in ["product", "item", "gallery"]):
                        main_image = src
                        break
        except: continue
            
    driver.quit()
    return results, main_image

# --- 3. UI LAYOUT ---
st.set_page_config(page_title="PricePro Universal", layout="wide")
conn = init_db()

# Sidebar: Connection Test & Summary
with st.sidebar:
    st.title("🛡️ PricePro Panel")
    if st.button("Check Browser Status"):
        with st.spinner("Testing..."):
            try:
                # Test with a simple site
                driver_test = scrape_multi_prices("https://www.google.com")
                st.success("Scraper Online")
            except Exception as e:
                st.error(f"Error: {str(e)}")
    
    st.divider()
    st.subheader("💰 Category Totals")
    summary = pd.read_sql_query("""
        SELECT c.name, SUM(p.price) as total FROM items i 
        JOIN categories c ON i.category_id = c.id 
        JOIN prices p ON p.item_id = i.id
        WHERE i.status = 'Watching' AND p.date = (SELECT MAX(date) FROM prices WHERE item_id = i.id)
        GROUP BY c.name""", conn)
    for _, row in summary.iterrows():
        st.sidebar.metric(row['name'], f"₱{row['total']:,.2f}")

# Main Navigation
tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "➕ Add Item", "📁 Categories"])

with tab3:
    st.subheader("Manage Categories")
    col1, col2 = st.columns([2,1])
    with col1:
        new_cat = st.text_input("New Category (e.g., 📱 Gadgets)")
    with col2:
        if st.button("Save Category") and new_cat:
            conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (new_cat,))
            conn.commit()
            st.rerun()

with tab2:
    st.subheader("Monitor New Product")
    cats = pd.read_sql_query("SELECT * FROM categories", conn)
    cat_dict = dict(zip(cats['name'], cats['id']))
    
    if not cat_dict:
        st.warning("Please create a category first in the 'Categories' tab.")
    else:
        with st.form("add_product"):
            name = st.text_input("Product Name")
            urls_input = st.text_area("Paste URLs (Separate with commas for comparison)")
            category = st.selectbox("Category", options=list(cat_dict.keys()))
            manual_p = st.number_input("Manual Price (Optional fallback)", min_value=0.0)
            
            if st.form_submit_button("Start Tracking"):
                with st.spinner("Analyzing pages..."):
                    results, img = scrape_multi_prices(urls_input)
                    
                    if not results and manual_p > 0:
                        results = [{"price": manual_p, "url": "Manual Entry"}]
                    
                    if results:
                        best_deal = min(results, key=lambda x: x['price'])
                        c = conn.cursor()
                        c.execute("INSERT INTO items (name, urls, image_url, status, category_id) VALUES (?,?,?,?,?)",
                                  (name, urls_input, img, 'Watching', cat_dict[category]))
                        c.execute("INSERT INTO prices (item_id, price, source_url, date) VALUES (?,?,?,?)",
                                  (c.lastrowid, best_deal['price'], best_deal['url'], datetime.now().strftime("%Y-%m-%d")))
                        conn.commit()
                        st.success("Tracking Active!")
                    else:
                        st.error("Could not find price. Try entering a Manual Price.")

with tab1:
    items = pd.read_sql_query("""
        SELECT i.*, c.name as cat_name FROM items i 
        JOIN categories c ON i.category_id = c.id 
        WHERE status='Watching'""", conn)
    
    if items.empty:
        st.info("No items tracked yet.")
    else:
        cols = st.columns(3)
        for idx, item in items.iterrows():
            with cols[idx % 3]:
                with st.container(border=True):
                    st.image(item['image_url'], use_container_width=True)
                    st.subheader(item['name'])
                    st.caption(f"📁 {item['cat_name']}")
                    
                    p_data = pd.read_sql_query(f"SELECT price, date FROM prices WHERE item_id={item['id']} ORDER BY date DESC", conn)
                    if not p_data.empty:
                        curr_p = p_data.iloc[0]['price']
                        st.metric("Lowest Price", f"₱{curr_p:,.2f}")
                        if len(p_data) > 1:
                            st.line_chart(p_data.set_index('date'), height=150)
                    
                    if st.button("Mark as Bought", key=f"btn_{item['id']}"):
                        conn.execute(f"UPDATE items SET status='Bought' WHERE id={item['id']}")
                        conn.commit()
                        st.rerun()
