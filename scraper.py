import os
import time
import json
import uuid
from pathlib import Path
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

OUTPUT_DIR = Path("static/outputs")

def scrape_ads_library(url: str, target_pages: int = 30, job_id: str = None, log_callback=None):
    if job_id is None:
        job_id = str(uuid.uuid4())[:8]
    
    job_dir = OUTPUT_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    
    def log(msg):
        print(msg, flush=True)
        if log_callback:
            log_callback(msg)
        try:
            with open(job_dir / "log.txt", "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except:
            pass
    
    with open(job_dir / "log.txt", "w", encoding="utf-8") as f:
        f.write("")
    
    log(f"Starting job {job_id}")
    log(f"URL: {url}")
    log(f"Target pages: {target_pages}")
    
    try:
        with sync_playwright() as p:
            log("Launching Chromium...")
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
            )
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            log("Opening Ads Library...")
            page.goto(url, wait_until="domcontentloaded", timeout=90000)
            log("Page loaded, waiting 7s for ads...")
            time.sleep(7)
            
            # Try close cookie banner
            try:
                sel = "button:has-text('Allow all cookies'), button:has-text('Accept All'), button:has-text('Allow all'), [data-testid='cookie-policy-manage-dialog-accept-button']"
                btn = page.locator(sel).first
                if btn.is_visible(timeout=2000):
                    btn.click()
                    log("Closed cookie banner")
                    time.sleep(1)
            except:
                pass
            
            for i in range(1, target_pages + 1):
                log(f"[{i}/{target_pages}] Scrolling...")
                try:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                except:
                    pass
                time.sleep(1.2)
                
                # Click see more buttons if any
                for sel in ["button:has-text('See more')", "button:has-text('Show more')"]:
                    try:
                        loc = page.locator(sel)
                        c = min(loc.count(), 2)
                        for j in range(c):
                            b = loc.nth(j)
                            if b.is_visible(timeout=500):
                                b.click(timeout=1500)
                                time.sleep(0.8)
                    except:
                        pass
                
                try:
                    page.mouse.wheel(0, 2500)
                except:
                    pass
                time.sleep(1.8)
                
                if i % 10 == 0:
                    try:
                        path = job_dir / f"progress_{i}_pages.png"
                        page.screenshot(path=str(path), full_page=True)
                        log(f"Saved progress {i} pages")
                    except Exception as e:
                        log(f"Screenshot progress failed: {e}")
            
            log("Taking final screenshot...")
            try:
                final_png = job_dir / "final_30_pages.png"
                page.screenshot(path=str(final_png), full_page=True)
                log(f"Saved final screenshot")
            except Exception as e:
                log(f"Final screenshot failed: {e}")
            
            log("Saving HTML...")
            try:
                html_content = page.content()
                with open(job_dir / "full_page.html", "w", encoding="utf-8") as f:
                    f.write(html_content)
                
                # Extract preview data
                soup = BeautifulSoup(html_content, "lxml")
                cards = soup.select("div[data-testid='ad-library-card']")
                if len(cards) < 10:
                    cards = soup.select("div[class*='x1yztbdb']")
                
                log(f"Found {len(cards)} potential ad elements")
                extracted = []
                for idx, card in enumerate(cards[:500]):
                    try:
                        text = card.get_text(separator=" ", strip=True)[:800]
                        if len(text) > 40:
                            extracted.append({"id": idx, "text_preview": text[:500]})
                    except:
                        pass
                
                with open(job_dir / "ads_data.json", "w", encoding="utf-8") as f:
                    json.dump({
                        "job_id": job_id,
                        "url": url,
                        "pages_loaded": target_pages,
                        "total_found": len(extracted),
                        "ads": extracted
                    }, f, indent=2, ensure_ascii=False)
                log(f"Saved {len(extracted)} ads to JSON")
            except Exception as e:
                log(f"Extraction error: {e}")
            
            browser.close()
        
        result = {
            "job_id": job_id,
            "status": "completed",
            "url": url,
            "pages": target_pages,
            "files": [f.name for f in job_dir.glob("*") if f.is_file()],
            "ads_count": len(extracted) if 'extracted' in locals() else 0
        }
        
        with open(job_dir / "result.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        
        log("✅ Done!")
        return result
        
    except Exception as e:
        log(f"❌ ERROR: {str(e)}")
        err_result = {
            "job_id": job_id,
            "status": "failed",
            "error": str(e),
            "url": url,
            "files": [f.name for f in job_dir.glob("*") if f.is_file()] if job_dir.exists() else []
        }
        try:
            with open(job_dir / "result.json", "w", encoding="utf-8") as f:
                json.dump(err_result, f, indent=2)
        except:
            pass
        return err_result

if __name__ == "__main__":
    import sys
    test_url = sys.argv[1] if len(sys.argv) > 1 else "https://web.facebook.com/ads/library/?active_status=active&ad_type=all&country=US&is_targeted_country=false&media_type=all&q=women%20fashion&search_type=keyword_unordered&sort_data[mode]=total_impressions&sort_data[direction]=desc"
    pages = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    scrape_ads_library(test_url, pages)
