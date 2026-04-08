import os
import re
import json
import time
import subprocess
from curl_cffi import requests
from bs4 import BeautifulSoup

def push_to_github():
    os.system('git add index.html script.py data/')
    status = subprocess.getoutput('git status --porcelain')
    if status.strip():
        os.system('git commit -m "Auto-update BEE dataset"')
        os.system('git push -u origin main')
        print("Data pushed to GitHub.")

def get_all_appliances(session):
    for _ in range(5):
        try:
            res = session.get("https://www.beestarlabel.com/SearchCompare", timeout=None)
            soup = BeautifulSoup(res.text, "html.parser")
            dropdown = soup.find("select", {"id": "Equipment"})
            return {opt.get("value"): opt.text.strip() for opt in dropdown.find_all("option") if opt.get("value") and opt.get("value") != "ALL"}
        except: time.sleep(10)
    return {}

def auto_discover_rules(session, eqcode):
    url = "https://www.beestarlabel.com/SearchCompare/LoadSearchView"
    for _ in range(5):
        try:
            res = session.post(url, json={"eqcode": str(eqcode)}, headers={"X-Requested-With": "XMLHttpRequest"}, timeout=None)
            match = re.search(r"var\s+serviceURL\s*=\s*['\"]([^'\"]+)['\"]", res.text)
            if not match: continue
            api_endpoint = "https://www.beestarlabel.com" + match.group(1)
            soup = BeautifulSoup(res.text, "html.parser")
            base_payload = {"eqcode": int(eqcode), "PDF": None, "fmodel": []}
            brands = [opt.get("value") for select in soup.find_all("select") if select.get("name") == "brand" for opt in select.find_all("option") if opt.get("value") and opt.get("value") != "ALL"]
            for select in soup.find_all("select"):
                if select.get("name"): base_payload[select.get("name")] = ["ALL"]
            return api_endpoint, base_payload, brands
        except: time.sleep(10)
    return None, None, []

def parse_cards(html_text, category_name, default_brand):
    extracted = []
    soup = BeautifulSoup(html_text, "html.parser")
    cards = soup.find_all(class_=re.compile(r"product-column|product-details|product-listing"))
    if not cards: cards = soup.find_all("li")

    for card in cards:
        h3 = card.find("h3")
        if not h3: continue
        
        star_rating = "0"
        img = h3.find("img")
        if img and img.get("src"):
            m = re.search(r'(\d+)\.gif', img.get("src"))
            if m: star_rating = m.group(1)
        
        parts = [t.strip() for t in h3.strings if t.strip()]
        brand = parts[0] if len(parts) > 0 else default_brand
        model = parts[1] if len(parts) > 1 else "Unknown"
        item = {"Category": category_name, "Brand": brand, "Model": model, "Star Rating": star_rating}
        
        details_area = card.find(class_=re.compile(r"content|body|detail|spec")) or card
        for el in details_area.find_all(['p', 'li', 'tr', 'div']):
            if el.name in ['div', 'tr'] and (el.find('p') or el.find('li')): continue
            
            lbl = el.find(['span', 'label', 'th', 'td'])
            val_tag = el.find(['strong', 'b', 'td'])
            if lbl and val_tag and lbl != val_tag:
                k = lbl.get_text(" ", strip=True).replace(":", "")
                v = val_tag.get_text(" ", strip=True)
                if k and v and not k.isdigit(): item[k] = v
            elif ":" in el.text:
                p = el.get_text(strip=True).split(":", 1)
                if len(p) == 2 and not p[0].strip().isdigit(): item[p[0].strip()] = p[1].strip()
        extracted.append(item)
    return extracted

def run_scraper():
    os.makedirs("data", exist_ok=True)
    session = requests.Session(impersonate="chrome110")
    appliances = get_all_appliances(session)
    if not appliances: return

    headers = {"Content-Type": "application/json; charset=utf-8", "X-Requested-With": "XMLHttpRequest"}

    for eqcode, name in appliances.items():
        safe_filename = f"data/{name.replace(' ', '_').replace('/', '_')}.json"
        if os.path.exists(safe_filename): continue
        
        api_endpoint, base_payload, brands = auto_discover_rules(session, eqcode)
        if not api_endpoint: continue
        
        appliance_data = []
        seen_items = set()

        for brand in brands:
            payload = {**base_payload, "brand": [brand]}
            try:
                res = session.post(api_endpoint, json=payload, headers=headers, timeout=None)
                if res.status_code == 200 and len(res.text.strip()) > 100:
                    for item in parse_cards(res.text, name, brand):
                        item_id = f"{item['Brand']}-{item['Model']}-{item['Star Rating']}"
                        if item_id not in seen_items:
                            appliance_data.append(item)
                            seen_items.add(item_id)
                else: raise Exception()
            except:
                for star in ["1", "2", "3", "4", "5"]:
                    try:
                        res = session.post(api_endpoint, json={**payload, "starlabel": [star]}, headers=headers, timeout=None)
                        if res.status_code == 200:
                            for item in parse_cards(res.text, name, brand):
                                item_id = f"{item['Brand']}-{item['Model']}-{item['Star Rating']}"
                                if item_id not in seen_items:
                                    appliance_data.append(item)
                                    seen_items.add(item_id)
                    except: pass
            time.sleep(1)

        with open(safe_filename, "w", encoding="utf-8") as f:
            json.dump(appliance_data, f, separators=(',', ':'))

    manifest_files = [f for f in os.listdir("data") if f.endswith(".json") and f != "manifest.json"]
    with open("data/manifest.json", "w") as f:
        json.dump(manifest_files, f)

    push_to_github()

if __name__ == "__main__":
    run_scraper()
