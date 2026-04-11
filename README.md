# BEE India Database

A high-performance scraper and web explorer for the Indian Bureau of Energy Efficiency (BEE) appliance database. 

This project extracts energy efficiency data (Star Ratings, Power Consumption, and Technical Specs) from the official BEE website and provides a searchable, mobile-friendly interface to browse thousands of products.

## 🚀 Links
* **[Live Explorer](https://vikyathkamathd.github.io/bee-india-database/)**

## ✨ Features
* **Universal Parser**: Deterministically extracts data from both table and card layouts on the BEE portal.
* **WAF Bypass**: Uses `curl_cffi` for TLS fingerprinting to ensure reliable extraction from local edge devices.
* **Parallel Processing**: Multi-threaded scraper that processes dozens of brands simultaneously.
* **Mobile-First UI**: A lightweight, reactive frontend built with Alpine.js and Tailwind CSS.
* **Deep Filtering**: Automatically generates filters based on technical specifications found in the dataset.

## 🛠️ Tech Stack
* **Scraper**: Python 3, `curl_cffi`, `beautifulsoup4`.
* **Frontend**: HTML5, Tailwind CSS, Alpine.js.
* **Storage**: GitHub (serving JSON files as a CDN).

## 💻 Run Locally

### 1. Prerequisites
Ensure you have Python 3.10+ installed.

### 2. Setup
```bash
git clone https://github.com/vikyathkamathd/bee-india-database.git
cd bee-india-database
pip install -r requirements.txt
```

### 3. Run Scraper
This will crawl the BEE website, generate JSON files in the `data/` folder, and update the web manifest.
```bash
python3 script.py
```

### 4. View Website
Simply open `index.html` in your browser or serve it using a local server:
```bash
python3 -m http.server 8000
```
