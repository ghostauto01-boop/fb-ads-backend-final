from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
import os
import uuid
import json
import threading
from pathlib import Path

# Import scraper
from scraper import scrape_ads_library, OUTPUT_DIR

app = Flask(__name__)
CORS(app)

# Ensure output dir exists at startup
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
(Path("static/outputs")).mkdir(parents=True, exist_ok=True)

jobs = {}

def run_job(job_id, url, pages):
    logs = []
    def log_cb(msg):
        logs.append(msg)
        if job_id in jobs:
            jobs[job_id]["logs"] = logs[-100:]
            jobs[job_id]["last_log"] = msg
    
    jobs[job_id] = {"status": "running", "logs": ["Starting..."], "url": url, "pages": pages}
    
    try:
        result = scrape_ads_library(url, pages, job_id=job_id, log_callback=log_cb)
        jobs[job_id].update(result)
        jobs[job_id]["status"] = result.get("status", "completed")
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/scrape", methods=["POST"])
def api_scrape():
    data = request.get_json() or {}
    url = data.get("url") or request.form.get("url")
    try:
        pages = int(data.get("pages") or request.form.get("pages") or 30)
    except:
        pages = 30
    
    if not url:
        return jsonify({"error": "URL required"}), 400
    if "facebook.com/ads/library" not in url:
        return jsonify({"error": "Please provide a valid Facebook Ads Library URL"}), 400
    if pages < 1 or pages > 100:
        return jsonify({"error": "Pages must be 1-100"}), 400
    
    job_id = str(uuid.uuid4())[:8]
    
    thread = threading.Thread(target=run_job, args=(job_id, url, pages), daemon=True)
    thread.start()
    
    return jsonify({"job_id": job_id, "status": "started"})

@app.route("/api/job/<job_id>")
def api_job_status(job_id):
    job_dir = OUTPUT_DIR / job_id
    if job_id in jobs:
        files = []
        if job_dir.exists():
            files = [f.name for f in job_dir.iterdir() if f.is_file()]
        return jsonify({**jobs[job_id], "files": files})
    
    result_path = job_dir / "result.json"
    if result_path.exists():
        try:
            with open(result_path) as f:
                result = json.load(f)
            log_path = job_dir / "log.txt"
            logs = []
            if log_path.exists():
                with open(log_path, encoding="utf-8") as lf:
                    logs = lf.read().splitlines()[-100:]
            return jsonify({**result, "logs": logs})
        except Exception as e:
            return jsonify({"error": f"Failed to read job: {e}"}), 500
    
    return jsonify({"error": "Job not found"}), 404

@app.route("/api/download/<job_id>/<filename>")
def download_file(job_id, filename):
    if ".." in filename or filename.startswith("/") or "/" in filename:
        return "Invalid filename", 400
    job_dir = OUTPUT_DIR / job_id
    if not (job_dir / filename).exists():
        return "File not found", 404
    return send_from_directory(job_dir, filename, as_attachment=True)

@app.route("/api/jobs")
def list_jobs():
    all_jobs = []
    if OUTPUT_DIR.exists():
        for d in OUTPUT_DIR.iterdir():
            if d.is_dir():
                result_path = d / "result.json"
                if result_path.exists():
                    try:
                        with open(result_path) as f:
                            all_jobs.append(json.load(f))
                    except:
                        pass
    return jsonify(sorted(all_jobs, key=lambda x: x.get("job_id",""), reverse=True))

@app.route("/health")
def health():
    return jsonify({"status": "ok", "message": "Backend is running"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True)
