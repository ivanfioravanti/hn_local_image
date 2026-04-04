import requests
import os
from bs4 import BeautifulSoup

def fetch_hn_headlines(max_stories: int = 30) -> list[str]:
    """Fetches the top stories from Hacker News."""
    hn_url = os.environ.get("HN_URL", "https://news.ycombinator.com/")
    headers = {"User-Agent": "hn_local_image/1.0"}
    response = requests.get(hn_url, headers=headers, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    # In HN HTML, story titles are within spans with class "titleline" which contain an "a" tag
    title_lines = soup.find_all("span", class_="titleline")
    
    titles = []
    for line in title_lines:
        a_tag = line.find("a")
        if a_tag and a_tag.text:
            titles.append(a_tag.text.strip())
            
        if len(titles) >= max_stories:
            break
            
    if not titles:
        raise ValueError("No stories found; Hacker News HTML may have changed.")
        
    return titles

if __name__ == "__main__":
    titles = fetch_hn_headlines(5)
    for i, t in enumerate(titles, 1):
        print(f"{i}. {t}")
