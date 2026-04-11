import os
import re
import json
import time
import subprocess
from curl_cffi import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

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
current_key_index = 0

def call_gemini(html_payload, category, brand):
    """Sends HTML to Gemini 2.5 Flash using strict Structured Outputs."""
    global current_key_index
    
    prompt = f"""
    Extract all appliance data from the following HTML into a JSON array.
    Default Category: "{category}"
    Default Brand: "{brand}"
    
    Ignore useless meta-text like 'Compare', 'View Details', 'Reviews/Feedback', or 'Valid Till Date'.
    """

    # Enforce strict JSON Schema output at the API level
    schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "Category": {"type": "STRING"},
                "Brand": {"type": "STRING"},
                "Model": {"type": "STRING"},
                "Star Rating": {"type": "STRING"}
            },
            "required": ["Category", "Brand", "Model", "Star Rating"],
            "additionalProperties": {"type": "STRING"} # Dynamically catches all other tech specs
        }
    }

    for _ in range(len(API_KEYS)):
        key = API_KEYS[current_key_index]
        client = genai.Client(api_key=key)
        
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=f"{prompt}\n\nHTML DATA:\n{html_payload}",
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0.0 # Force deterministic output
                )
            )
            return json.loads(response.text)
            
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "quota" in err_str or "exhausted" in err_str:
                print("   ⏳ Rate limit hit! Switching API key...")
                current_key_index = (current_key_index + 1) % len(API_KEYS)
                continue # Try immediately with the next key
            else:
                print(f"   ⚠️ API Error: {e}")
                return []
                
    print("   🚨 All API keys rate-limited! Sleeping for 60 seconds...")
    time.sleep(60)
    return []

# --- EXTRACTOR ---
def parse_cards_with_ai(html_text, category_name, default_brand):
    """Cleans the HTML and routes to the Gemini SDK."""
    soup = BeautifulSoup(html_text, "html.parser")
    
    for tag in soup(["script", "style", "img", "svg", "noscript", "meta"]):
        tag.decompose()
        
    container = soup.find(class_=re.compile(r"product|list|grid|result")) or soup.body
    clean_html = str(container)[:50000] 
    
    return call_gemini(clean_html, category_name, default_brand)

def push_to_github():
    os.system('git add index.html script.py data/ .gitignore')
    status = subprocess.getoutput('git status --porcelain')
    if status.strip():
        os.system('git commit -m "Auto-update dataset using Gemini 2.5 Flash SDK"')
        os.system('git push -u origin main')
        print("🚀 LIVE WEBSITE UPDATED SUCCESSFULLY!")
    else:
        print("🤷‍♂️ No new data to upload.")

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

def run_scraper():
    print(f"🔑 Loaded {len(API_KEYS)} Gemini API Key(s).")
    os.makedirs("data", exist_ok=True)
    session = requests.Session(impersonate="chrome110")
    print("🤖 Connecting to BEE Server via Local IP...")
    appliances = get_all_appliances(session)
    if not appliances: return

    headers = {"Content-Type": "application/json; charset=utf-8", "X-Requested-With": "XMLHttpRequest"}

    for eqcode, name in appliances.items():
        safe_filename = f"data/{name.replace(' ', '_').replace('/', '_')}.json"
        if os.path.exists(safe_filename): continue
        
        print(f"🚀 AI Extracting: {name}...")
        api_endpoint, base_payload, brands = auto_discover_rules(session, eqcode)
        if not api_endpoint: continue
        
        appliance_data = []
        seen_items = set()

        for brand in brands:
            payload = {**base_payload, "brand": [brand]}
            try:
                res = session.post(api_endpoint, json=payload, headers=headers, timeout=None)
                if res.status_code == 200 and len(res.text.strip()) > 100:
                    ai_results = parse_cards_with_ai(res.text, name, brand)
                    
                    for item in ai_results:
                        item_id = f"{item.get('Brand', 'Unk')}-{item.get('Model', 'Unk')}-{item.get('Star Rating', '0')}"
                        if item_id not in seen_items:
                            appliance_data.append(item)
                            seen_items.add(item_id)
                else: raise Exception()
            except Exception as e:
                pass 
            time.sleep(1) 

        if appliance_data:
            with open(safe_filename, "w", encoding="utf-8") as f:
                json.dump(appliance_data, f, separators=(',', ':'))
            print(f"   ✅ AI Saved {len(appliance_data)} perfect items")

    print("🛠️ Generating manifest...")
    manifest_files = [f for f in os.listdir("data") if f.endswith(".json") and f != "manifest.json"]
    with open("data/manifest.json", "w") as f:
        json.dump(manifest_files, f)

    push_to_github()

if __name__ == "__main__":
    run_scraper()
