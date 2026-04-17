# BEE India Database

A scraper and optimized website for browsing the Indian Bureau of Energy Efficiency (BEE) appliance database.

This project extracts energy efficiency data (Star Ratings, Power Consumption, and Technical Specs) from the official BEE website and provides a searchable, interface to browse bee star rated products.

## Run Locally

### 1. Prerequisites
Ensure you have Python 3.10+ installed.

### 2. Setup
```bash
git clone https://github.com/vikyathkamathd/bee-india-database.git
cd bee-india-database
pip install -r requirements.txt
```
recommended to run in python venv

### 3. Run Scraper
This will crawl the BEE website, generate JSON files in the `data/` folder, and update the web manifest.
```bash
python3 script.py
```

### 4. View Website
serve it using a local server:
```bash
python3 -m http.server 8000
```
open in browser with local host port 8000
