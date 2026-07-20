from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from core.interfaces import ICrawlProvider

class PlaywrightCrawlProvider(ICrawlProvider):
    def __init__(self, timeout: int = 15):
        self.timeout = timeout * 1000  # Playwright uses milliseconds

    def fetch(self, url: str) -> str:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080}
            )
            page = context.new_page()
            try:
                # Load the page and wait for initial DOM
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
                except Exception as e:
                    print(f"Goto timeout or error for {url}: {e}, attempting to read whatever loaded.")
                
                # Wait 3 seconds for JS frameworks to render data
                page.wait_for_timeout(3000)
                
                # Stop any further loading which might prevent page.content() from succeeding
                page.evaluate("window.stop()")
                
                html = page.content()
                
                soup = BeautifulSoup(html, 'html.parser')
                for script in soup(["script", "style", "noscript", "svg"]):
                    script.extract()
                    
                text = soup.get_text(separator=' ', strip=True)
                return text
                
            except Exception as e:
                raise Exception(f"Failed to crawl {url} with Playwright: {str(e)}")
            finally:
                context.close()
                browser.close()
