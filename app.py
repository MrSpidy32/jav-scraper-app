import os
from flask import Flask, render_template, request, jsonify
import asyncio

# Import our scraper
from javdb.api import JAVScraper

app = Flask(__name__, template_folder="templates")

@app.route("/", methods=["GET"])
def index():
    """Serve the modern web UI."""
    return render_template("index.html")

@app.route("/api/scrape", methods=["GET"])
async def scrape_movie():
    """API endpoint used by the UI to fetch movie data."""
    dvd_id = request.args.get("dvd_id")
    proxy = request.args.get("proxy")
    
    if not dvd_id:
        return jsonify({"detail": "dvd_id parameter is required"}), 400

    async with JAVScraper(proxy=proxy) as scraper:
        result = await scraper.scrape(dvd_id)
        
        if result.success and result.movie:
            return jsonify(result.movie.model_dump())
        else:
            return jsonify({
                "detail": f"Failed to find {dvd_id}. Errors: {', '.join(result.errors)}"
            }), 404

if __name__ == "__main__":
    print("Starting Web UI on http://localhost:8000")
    app.run(host="0.0.0.0", port=8000, debug=True)
