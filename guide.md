# Deployment Guide: JAV Ultimate Scraper

This guide explains how to host your scraper application (which includes both the API and the web UI) on modern cloud platforms like Render, Railway, Koyeb, or a self-hosted VPS. 

I've reorganized the code into a **standard web application structure**, meaning you no longer have to worry about "package folders" or import errors.

## Folder Structure Explained
Your project is now in `/tmp/jav-scraper-app/`. It looks like this:
```text
jav-scraper-app/
├── app.py              # The main Flask web server (UI & API)
├── requirements.txt    # Python dependencies (now includes gunicorn)
├── Procfile            # Tells cloud providers how to start the app
├── templates/          # Contains the index.html UI file
├── javdb/              # The scraper logic package
│   ├── api.py          
│   ├── merger.py       
│   └── scrapers/       
└── guide.md            # This file!
```

---

## Step 1: Upload to GitHub
Before deploying to most cloud platforms, you need to push this code to a GitHub repository.
1. Go to GitHub and create a new Private or Public repository (e.g., `jav-scraper-app`).
2. On your machine (or wherever this code is), initialize Git and push:
```bash
cd /tmp/jav-scraper-app
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/jav-scraper-app.git
git push -u origin main
```

---

## Step 2: Deploy to a Cloud Provider

### Option A: Deploy on Render.com (Easiest & Free Tier)
1. Sign in to [Render](https://render.com/).
2. Click **New +** and select **Web Service**.
3. Connect your GitHub account and select your `jav-scraper-app` repository.
4. Fill in the settings:
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
5. Select the **Free** instance type and click **Create Web Service**.
6. Render will build and deploy your app. You'll get a URL like `https://jav-scraper.onrender.com`.

### Option B: Deploy on Railway.app
Railway is extremely fast and automatically detects Python apps.
1. Sign in to [Railway](https://railway.app/).
2. Click **New Project** -> **Deploy from GitHub repo**.
3. Select your `jav-scraper-app` repository.
4. Click **Deploy Now**. 
5. Railway will automatically read your `Procfile` and `requirements.txt` and start the app.
6. Go to the **Settings** tab -> **Domains** -> click **Generate Domain** to get your public URL.

### Option C: Deploy on Koyeb
1. Sign in to [Koyeb](https://www.koyeb.com/).
2. Click **Create App** and choose **GitHub**.
3. Select your repository.
4. In the Builder configuration, it will auto-detect Python. 
5. **Run Command:** Type `gunicorn app:app` (or it will auto-read the `Procfile`).
6. Click **Deploy**.

---

## Option D: Self-Hosting on a VPS (Ubuntu/Debian)
If you bought a VPS (DigitalOcean, Hetzner, Linode) to avoid datacenter Cloudflare blocks, here is how you host it yourself.

1. SSH into your server:
```bash
ssh root@your_server_ip
```

2. Update your server and install Python:
```bash
apt update && apt upgrade -y
apt install python3 python3-pip python3-venv git -y
```

3. Clone your code (or copy it over via SFTP):
```bash
git clone https://github.com/YOUR_USERNAME/jav-scraper-app.git
cd jav-scraper-app
```

4. Create a virtual environment and install dependencies:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

5. Run it in the background using `gunicorn`:
```bash
gunicorn app:app --bind 0.0.0.0:80 --workers 2 --threads 4 --daemon
```
Now, if you visit your server's IP address in your browser (e.g., `http://123.45.67.89`), you will see the UI!

*(Note: For a robust production setup on a VPS, you should set up Nginx as a reverse proxy and Systemd to keep it running forever. There are thousands of guides online for "Deploying Flask with Gunicorn and Nginx".)*

---

## Important Note on Cloudflare
If you deploy to a datacenter (like Render or Railway), their IP addresses are sometimes blocked by Cloudflare (which protects JavLibrary and JavDB).

If your deployed app keeps failing to scrape, you will need to add a proxy.
1. Buy a cheap residential or rotating proxy.
2. In your Flask `app.py`, hardcode the proxy into the scraper like this:
```python
async with JAVScraper(proxy="http://user:pass@proxy.example.com:8000") as scraper:
```