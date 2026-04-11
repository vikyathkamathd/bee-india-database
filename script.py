import os
import re
import json
import time
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from curl_cffi import requests
from bs4 import BeautifulSoup

# --- CONFIG ---
TEST_MODE = False # Set to False for full run

def extract_product_data(html_text, category, brand):
    """Deterministically extracts data from both BEE's Table and List/Card structures."""
    soup = BeautifulSoup(html_text, "html.parser")
    results = []

    # --- CASE 1: Table Structure ---
    table = soup.find("table")
    if table:
        rows = table.find_all("tr")
        if rows:
            headers = [h.get_text(strip=True) for h in rows[0].find_all(["th", "td"])]
            model_idx = -1
            star_idx = -1
            for i, h in enumerate(headers):
                h_low = h.lower()
                if "model" in h_low: model_idx = i
                if "star" in h_low and "rating" in h_low: star_idx = i

            for row in rows[1:]:
                cols = row.find_all("td")
                if len(cols) < len(headers): continue
                item = {"Category": category, "Brand": brand}
                for i, col in enumerate(cols):
                    if i < len(headers):
                        val = col.get_text(strip=True)
                        key = headers[i]
                        if i == model_idx: item["Model"] = val
                        elif i == star_idx: item["Star Rating"] = val
                        else: item[key] = val
                if "Model" not in item: item["Model"] = "Unknown"
                if "Star Rating" not in item: item["Star Rating"] = "0"
                results.append(item)
            if results: return results

    # --- CASE 2: List/Card Structure (ul.show-product-listing) ---
    listing = soup.find("ul", class_=re.compile(r"show-product-listing|product-list", re.I))
    if listing:
        cards = listing.find_all("li")
        for card in cards:
            item = {"Category": category, "Brand": brand}
            
            # Extract Star Rating from Image Filename (e.g., 2.gif -> 2)
            img = card.find("img")
            if img and img.get("src"):
                match = re.search(r"/(\d+)\.gif", img.get("src"))
                item["Star Rating"] = match.group(1) if match else "0"
            else:
                item["Star Rating"] = "0"

            # Extract Brand/Model from H3
            h3 = card.find("h3")
            if h3:
                # Text usually looks like "BRAND\nMODEL" or has multiple <br>
                parts = [p.strip() for p in h3.get_text(separator="|").split("|") if p.strip()]
                # Typically [Brand, Model]
                if len(parts) >= 2:
                    item["Brand"] = parts[0]
                    item["Model"] = parts[1]
                elif len(parts) == 1:
                    item["Model"] = parts[0]
            
            # Extract Technical Specs from P tags
            specs = card.find_all("p")
            for p in specs:
                # Usually: SPEC NAME <br> <strong>VALUE</strong>
                strong = p.find("strong")
                if strong:
                    key = p.get_text().replace(strong.get_text(), "").strip()
                    if key:
                        item[key] = strong.get_text(strip=True)
            
            if "Model" in item:
                results.append(item)
        
    return results

def update_manifest():
    """Updates manifest.json for the frontend."""
    os.makedirs("data", exist_ok=True)
    files = [f for f in os.listdir("data") if f.endswith(".json") and f != "manifest.json"]
    with open("data/manifest.json", "w") as f:
        json.dump(files, f)

def push_to_github():
    """Pushes updates to GitHub."""
    os.system('git add index.html script.py data/ .gitignore')
    if subprocess.getoutput('git status --porcelain').strip():
        os.system('git commit -m "Auto-update using Universal Parser"')
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
    payload = {**base_payload, "brand": [brand]}
    full_headers = {
        **headers,
        "Referer": "https://www.beestarlabel.com/SearchCompare",
        "Origin": "https://www.beestarlabel.com",
        "X-Requested-With": "XMLHttpRequest"
    }
    try:
        res = session.post(api_endpoint, json=payload, headers=full_headers, timeout=30)
        if res.status_code == 200:
            return extract_product_data(res.text, name, brand)
    except: pass
    return []

def run_scraper():
    os.makedirs("data", exist_ok=True)
    session = requests.Session(impersonate="chrome110")
    print("🤖 Connecting to BEE Server...")
    appliances = get_all_appliances(session)
    if not appliances: return

    headers = {"Content-Type": "application/json; charset=utf-8", "X-Requested-With": "XMLHttpRequest"}

    for i, (eqcode, name) in enumerate(appliances.items()):
        if TEST_MODE and i >= 1: break
        
        safe_filename = f"data/{name.replace(' ', '_').replace('/', '_')}.json"
        print(f"🚀 Category: {name}")
        
        api_endpoint, base_payload, brands = auto_discover_rules(session, eqcode)
        if not api_endpoint: continue
        
        if TEST_MODE: brands = brands[:3]
        
        appliance_data = []
        seen_items = set()
        new_items_found = False

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {executor.submit(process_brand, session, api_endpoint, base_payload, headers, b, name): b for b in brands}
            
            for future in as_completed(futures):
                brand_results = future.result()
                if brand_results:
                    for item in brand_results:
                        item_id = f"{item.get('Brand', 'Unk')}-{item.get('Model', 'Unk')}-{item.get('Star Rating', '0')}"
                        if item_id not in seen_items:
                            appliance_data.append(item)
                            seen_items.add(item_id)
                            new_items_found = True

        if new_items_found:
            with open(safe_filename, "w", encoding="utf-8") as f:
                json.dump(appliance_data, f, separators=(',', ':'))
            print(f"   ✅ Saved {len(appliance_data)} items")
            update_manifest()
        else:
            print(f"   ⏭️ No new data")

    print("🛠️ Finalizing...")
    update_manifest()
    if not TEST_MODE:
        push_to_github()

if __name__ == "__main__":
    run_scraper()
