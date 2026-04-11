import os
import re
import json
import time
import datetime
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from curl_cffi import requests
from bs4 import BeautifulSoup

def extract_product_data(html_text, category, brand):
    """Deterministically extracts data from BEE's Table and Card structures."""
    soup = BeautifulSoup(html_text, "html.parser")
    results = []

    # Case 1: Table Structure
    table = soup.find("table")
    if table:
        rows = table.find_all("tr")
        if rows:
            headers = [h.get_text(strip=True) for h in rows[0].find_all(["th", "td"])]
            indices = {h.lower(): i for i, h in enumerate(headers)}
            
            model_idx = next((i for k, i in indices.items() if "model" in k), -1)
            star_idx = next((i for k, i in indices.items() if "star" in k and "rating" in k), -1)

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
                item.setdefault("Model", "Unknown")
                item.setdefault("Star Rating", "0")
                results.append(item)
            if results: return results

    # Case 2: List/Card Structure
    listing = soup.find("ul", class_=re.compile(r"show-product-listing|product-list", re.I))
    if listing:
        for card in listing.find_all("li"):
            item = {"Category": category, "Brand": brand}
            img = card.find("img")
            if img and img.get("src"):
                match = re.search(r"/(\d+)\.gif", img.get("src"))
                item["Star Rating"] = match.group(1) if match else "0"
            
            h3 = card.find("h3")
            if h3:
                parts = [p.strip() for p in h3.get_text(separator="|").split("|") if p.strip()]
                if len(parts) >= 2:
                    item["Brand"], item["Model"] = parts[0], parts[1]
                elif len(parts) == 1:
                    item["Model"] = parts[0]
            
            for p in card.find_all("p"):
                strong = p.find("strong")
                if strong:
                    key = p.get_text().replace(strong.get_text(), "").strip()
                    if key: item[key] = strong.get_text(strip=True)
            
            if "Model" in item:
                results.append(item)
    return results

def update_manifest():
    """Updates manifest.json with file list and last update timestamp."""
    os.makedirs("data", exist_ok=True)
    files = [f for f in os.listdir("data") if f.endswith(".json") and f != "manifest.json"]
    manifest = {
        "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "files": files
    }
    with open("data/manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

def push_to_github():
    """Commits and pushes all project updates to GitHub."""
    os.system('git add .')
    if subprocess.getoutput('git status --porcelain').strip():
        os.system('git commit -m "Final project cleanup & README update"')
        os.system('git push -u origin main')


def get_all_appliances(session):
    try:
        res = session.get("https://www.beestarlabel.com/SearchCompare", timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        dropdown = soup.find("select", {"id": "Equipment"})
        return {opt.get("value"): opt.text.strip() for opt in dropdown.find_all("option") if opt.get("value") and opt.get("value") != "ALL"}
    except: return {}

def auto_discover_rules(session, eqcode):
    url = "https://www.beestarlabel.com/SearchCompare/LoadSearchView"
    try:
        res = session.post(url, json={"eqcode": str(eqcode)}, headers={"X-Requested-With": "XMLHttpRequest"}, timeout=15)
        match = re.search(r"var\s+serviceURL\s*=\s*['\"]([^'\"]+)['\"]", res.text)
        if not match: return None, None, []
        api_endpoint = "https://www.beestarlabel.com" + match.group(1)
        soup = BeautifulSoup(res.text, "html.parser")
        base_payload = {"eqcode": int(eqcode), "PDF": None, "fmodel": []}
        brands = [opt.get("value") for select in soup.find_all("select") if select.get("name") == "brand" for opt in select.find_all("option") if opt.get("value") and opt.get("value") != "ALL"]
        for select in soup.find_all("select"):
            if select.get("name"): base_payload[select.get("name")] = ["ALL"]
        return api_endpoint, base_payload, brands
    except: return None, None, []

def process_brand(session, api_endpoint, base_payload, brand, name):
    payload = {**base_payload, "brand": [brand]}
    headers = {"Referer": "https://www.beestarlabel.com/SearchCompare", "X-Requested-With": "XMLHttpRequest"}
    try:
        res = session.post(api_endpoint, json=payload, headers=headers, timeout=30)
        if res.status_code == 200: return extract_product_data(res.text, name, brand)
    except: pass
    return []

def run_scraper():
    os.makedirs("data", exist_ok=True)
    session = requests.Session(impersonate="chrome110")
    print("🤖 Initializing BEE Scraper...")
    appliances = get_all_appliances(session)
    if not appliances: return

    for eqcode, name in appliances.items():
        safe_filename = f"data/{name.replace(' ', '_').replace('/', '_')}.json"
        print(f"🚀 Processing: {name}")
        
        api_endpoint, base_payload, brands = auto_discover_rules(session, eqcode)
        if not api_endpoint: continue
        
        appliance_data = []
        seen_items = set()
        new_data = False

        with ThreadPoolExecutor(max_workers=15) as executor:
            futures = {executor.submit(process_brand, session, api_endpoint, base_payload, b, name): b for b in brands}
            for future in as_completed(futures):
                results = future.result()
                if results:
                    for item in results:
                        item_id = f"{item.get('Brand')}-{item.get('Model')}-{item.get('Star Rating')}"
                        if item_id not in seen_items:
                            appliance_data.append(item); seen_items.add(item_id); new_data = True

        if new_data:
            with open(safe_filename, "w", encoding="utf-8") as f:
                json.dump(appliance_data, f, separators=(',', ':'))
            print(f"   ✅ Saved {len(appliance_data)} items")
            update_manifest()

    print("🛠️ Finalizing...")
    update_manifest()
    push_to_github()

if __name__ == "__main__":
    run_scraper()
