import os
import re
import json
import time
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from curl_cffi import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

# --- CONFIG ---
TEST_MODE = True # Set to False for full run

# --- SHARED STATE & LOCKS ---
key_lock = threading.Lock()
current_key_index = 0

# --- API KEY MANAGER ---
def get_api_keys():
    if not os.path.exists("api_keys.txt"):
        print("🚨 ERROR: api_keys.txt not found!")
        exit(1)
    with open("api_keys.txt", "r") as f:
        keys = [line.strip() for line in f if line.strip()]
    if not keys:
        print("🚨 ERROR: api_keys.txt is empty!")
        exit(1)
    return keys

API_KEYS = get_api_keys()

def call_gemini(html_payload, category, brand):
    """Sends HTML to Gemma 4 using JSON Mode (supports dynamic keys)."""
    global current_key_index
    
    prompt = f"""
    Extract all appliance data from the provided HTML into a JSON array of flat objects.
    CONTEXT: Category="{category}", Brand="{brand}"
    
    RULES:
    1. Output MUST be a valid JSON array of objects.
    2. Every object MUST have: 'Category', 'Brand', 'Model', and 'Star Rating'.
    3. Extract all other technical specifications as direct key-value pairs in the same object.
    4. Keep the structure flat. Ignore 'View Details' or 'Compare'.
    """

    while True:
        with key_lock:
            key = API_KEYS[current_key_index]
        client = genai.Client(api_key=key)
        
        try:
            response = client.models.generate_content(
                model='models/gemma-4-31b-it',
                contents=f"{prompt}\n\nHTML DATA:\n{html_payload}",
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0
                )
            )
            return json.loads(response.text)
            
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "quota" in err_str or "exhausted" in err_str:
                with key_lock:
                    current_key_index = (current_key_index + 1) % len(API_KEYS)
                    if current_key_index == 0:
                        time.sleep(5) # Reduced sleep for faster rotation
                continue 
            return []

# --- EXTRACTOR ---
def parse_cards_with_ai(html_text, category_name, default_brand):
    """Broadens card detection to handle BEE's table structure."""
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style", "img", "svg", "noscript", "meta"]): tag.decompose()
    
    # Try finding specific product cards first
    cards = soup.find_all(["tr", "div"], class_=re.compile(r"product|item|row|card|result", re.I))
    
    # FALLBACK: If no cards found, take all table rows (BEE standard)
    if not cards:
        cards = soup.find_all("tr")
        # Broaden to include all rows with ANY text
        cards = [c for c in cards if len(c.get_text(strip=True)) > 5]

    if not cards:
        return call_gemini(str(soup.body)[:500000], category_name, default_brand)

    # Filter out header rows (often contain "Model" or "Brand" text)
    data_cards = []
    for c in cards:
        txt = c.get_text().lower()
        if "model" in txt and "brand" in txt and len(txt) < 100: continue # Likely header
        data_cards.append(c)
    
    cards = data_cards
    print(f"      🔍 Found {len(cards)} items to process.")

    # 50 cards per call is safer for response length
    chunk_size = 50 
    all_results = []
    
    for i in range(0, len(cards), chunk_size):
        chunk_html = "".join(str(c) for c in cards[i : i + chunk_size])
        print(f"      📦 Processing chunk {i//chunk_size + 1}/{(len(cards)-1)//chunk_size + 1}...")
        res = call_gemini(chunk_html, category_name, default_brand)
        if res: 
            print(f"         ✅ Extracted {len(res)} items")
            all_results.extend(res)
        else:
            print(f"         ⚠️ Chunk {i//chunk_size + 1} failed (returned empty)")
            
    return all_results

def update_manifest():
    manifest_files = [f for f in os.listdir("data") if f.endswith(".json") and f != "manifest.json"]
    with open("data/manifest.json", "w") as f:
        json.dump(manifest_files, f)

def push_to_github():
    os.system('git add index.html script.py data/ .gitignore')
    status = subprocess.getoutput('git status --porcelain')
    if status.strip():
        os.system('git commit -m "Auto-update dataset using Gemma 4 31B"')
        os.system('git push -u origin main')

def get_all_appliances(session):
    for _ in range(5):
        try:
            res = session.get("https://www.beestarlabel.com/SearchCompare", timeout=15)
            soup = BeautifulSoup(res.text, "html.parser")
            dropdown = soup.find("select", {"id": "Equipment"})
            return {opt.get("value"): opt.text.strip() for opt in dropdown.find_all("option") if opt.get("value") and opt.get("value") != "ALL"}
        except: time.sleep(2)
    return {}

def auto_discover_rules(session, eqcode):
    url = "https://www.beestarlabel.com/SearchCompare/LoadSearchView"
    for _ in range(5):
        try:
            res = session.post(url, json={"eqcode": str(eqcode)}, headers={"X-Requested-With": "XMLHttpRequest"}, timeout=15)
            match = re.search(r"var\s+serviceURL\s*=\s*['\"]([^'\"]+)['\"]", res.text)
            if not match: continue
            api_endpoint = "https://www.beestarlabel.com" + match.group(1)
            soup = BeautifulSoup(res.text, "html.parser")
            base_payload = {"eqcode": int(eqcode), "PDF": None, "fmodel": []}
            brands = [opt.get("value") for select in soup.find_all("select") if select.get("name") == "brand" for opt in select.find_all("option") if opt.get("value") and opt.get("value") != "ALL"]
            for select in soup.find_all("select"):
                if select.get("name"): base_payload[select.get("name")] = ["ALL"]
            return api_endpoint, base_payload, brands
        except: time.sleep(2)
    return None, None, []

def process_brand(session, api_endpoint, base_payload, headers, brand, name):
    """Worker function to process a single brand."""
    payload = {**base_payload, "brand": [brand]}
    try:
        res = session.post(api_endpoint, json=payload, headers=headers, timeout=30)
        if res.status_code == 200 and len(res.text.strip()) > 100:
            print(f"      📡 Brand: {brand} ({len(res.text)} bytes)")
            return parse_cards_with_ai(res.text, name, brand)
    except: pass
    return []

def run_scraper():
    print(f"🔑 Loaded {len(API_KEYS)} API Key(s).")
    os.makedirs("data", exist_ok=True)
    session = requests.Session(impersonate="chrome110")
    print("🤖 Connecting to BEE Server...")
    appliances = get_all_appliances(session)
    if not appliances: return

    headers = {"Content-Type": "application/json; charset=utf-8", "X-Requested-With": "XMLHttpRequest"}

    for i, (eqcode, name) in enumerate(appliances.items()):
        if TEST_MODE and i >= 1: break # Only 1 category in test mode
        
        safe_filename = f"data/{name.replace(' ', '_').replace('/', '_')}.json"
        print(f"🚀 Category: {name}")
        
        api_endpoint, base_payload, brands = auto_discover_rules(session, eqcode)
        if not api_endpoint: continue
        
        if TEST_MODE: brands = brands[:3] # Only 3 brands in test mode
        
        appliance_data = []
        seen_items = set()
        new_items_found = False

        # Parallelize Brand Processing (10 brands at a time)
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(process_brand, session, api_endpoint, base_payload, headers, b, name): b for b in brands}
            
            for future in as_completed(futures):
                brand_results = future.result()
                if brand_results:
                    for item in brand_results:
                        # Deduplicate
                        item_id = f"{item.get('Brand', 'Unk')}-{item.get('Model', 'Unk')}-{item.get('Star Rating', '0')}"
                        if item_id not in seen_items:
                            appliance_data.append(item)
                            seen_items.add(item_id)
                            new_items_found = True

        if new_items_found:
            with open(safe_filename, "w", encoding="utf-8") as f:
                json.dump(appliance_data, f, separators=(',', ':'))
            print(f"   ✅ Saved {len(appliance_data)} items for {name}")
            update_manifest()
        else:
            print(f"   ⏭️ No new data for {name}")

    print("🛠️ Finalizing...")
    update_manifest()
    push_to_github()

if __name__ == "__main__":
    run_scraper()
