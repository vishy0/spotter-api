# Fuel Route Optimizer API

A lightweight, stateless Django REST microservice that calculates driving routes across the continental United States and identifies the optimal, cost-effective fuel stops along the way to minimize total trip expenditure.

Designed with a **zero-key** and **zero-external-database** architecture for an effortless reviewer evaluation experience.

---


## Quick Start

### Option A: Local Python Environment (Recommended)

1. **Clone and enter the directory:**
   ```bash
   git clone <repo-url>
   cd spotter-api
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate      # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Initialize database & start development server:**
   ```bash
   python manage.py migrate
   python manage.py runserver
   ```

---

### Option B: Docker Compose

Spin up the entire application inside Docker with a single command:
```bash
docker compose up --build
```
Navigate to `http://localhost:8000/map/` in your browser.

---

## Interactive Visualizer

Visit the built-in Leaflet visual map in your browser:
```
http://localhost:8000/map/
```
* Preloaded with quick presets: *Austin &rarr; Houston* (< 500 mi), *Dallas &rarr; Atlanta* (~780 mi), and *LA &rarr; NYC* (Coast-to-Coast).
* Displays highway geometry, click-to-zoom fuel pins, live popups with pricing and gallons to buy, and a real-time financial scorecard.

---
