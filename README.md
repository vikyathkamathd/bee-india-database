# bee-india-database

A high-performance, automated web scraper and mobile-first frontend for the Indian Bureau of Energy Efficiency (BEE) database. 

This project extracts appliance energy efficiency data (Star Ratings, Power Consumption, Capacities, etc.) from the official BEE website and serves it through a lightning-fast, highly optimized web interface.

## Features

* Fully Automated Pipeline: A GitHub Action runs daily to scrape the latest data, handle server timeouts, and commit the fresh data as minified JSON.
* Mobile-First UI: Built to mimic native shopping apps (like Amazon/Flipkart) with a clean, bottom-sheet driven interface.
* Deep Data Parsing: Bypasses basic HTML structures to extract deep technical specifications (e.g., Cooling Method, ISEER, Rated Capacity).
* Zero-Lag Performance: Uses Virtual Pagination (Infinite Scroll) and debounced searching to handle thousands of products without crashing mobile browsers.
* Dynamic Filtering: Automatically generates technical specification filters based on the raw dataset.

## Tech Stack

**Backend / Extraction:**
* Python 3.10
* `curl_cffi` 
* `beautifulsoup4`

**Frontend:**
* HTML5 / Vanilla JavaScript
* Tailwind CSS
* Alpine.js

## Live Demo

**[View the Live Explorer Here](https://vikyathkamathd.github.io/bee-india-database/)** *(Note: Data is updated automatically every midnight UTC).*
