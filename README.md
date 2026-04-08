# bee-india-database

A high-performance web scraper and mobile-first frontend for the Indian Bureau of Energy Efficiency (BEE) database. 

This project extracts appliance energy efficiency data (Star Ratings, Power Consumption, Capacities, etc.) from the official BEE website and serves it through a lightning-fast, highly optimized web interface.

## Links
* **[View the Live Explorer Here](https://vikyathkamathd.github.io/bee-india-database/)**

## The Edge Scraper Architecture (WAF Bypass)
Initially built with cloud-based CI/CD pipelines, the extraction engine was blocked by the Indian Government's Web Application Firewall (WAF), which geo-blocks large international datacenters to prevent bot attacks. 

**The Solution:** The extraction engine (`script.py`) runs locally on an edge device. By utilizing a local Indian telecom IP address, it acts as an "Edge Server" to successfully bypass the WAF, extract the JSON data, and automatically push the fresh dataset directly to GitHub, which serves as the global CDN for the frontend.

## Features

* **WAF-Bypassing Extraction:** Utilizes `curl_cffi` for TLS fingerprinting and an edge-device execution model to reliably extract data without triggering security blocks.
* **Mobile-First UI:** Built to mimic native shopping apps with a clean, bottom-sheet driven interface.
* **Deep Data Parsing:** Bypasses basic HTML structures to extract deep technical specifications (e.g., Cooling Method, ISEER, Rated Capacity).
* **Zero-Lag Performance:** Uses Virtual Pagination (Infinite Scroll) and debounced searching to handle thousands of products without crashing mobile browsers.
* **Dynamic Filtering:** Automatically generates technical specification filters based on the raw JSON dataset.

## Tech Stack

**Backend / Data Pipeline:**
* Python 3
* `curl_cffi` (for TLS spoofing)
* `beautifulsoup4` (for DOM parsing)
* Git (for automated state management and CDN deployment)

**Frontend:**
* HTML5 / Vanilla JavaScript
* Tailwind CSS
* Alpine.js (for lightweight, reactive state management)

## Run Locally

To run the edge-scraper pipeline yourself:

1. Ensure Python and Git are installed on your device.
2. Clone the repository:
   ```bash
   git clone [https://github.com/vikyathkamathd/bee-india-database.git](https://github.com/vikyathkamathd/bee-india-database.git)
   cd bee-india-database
