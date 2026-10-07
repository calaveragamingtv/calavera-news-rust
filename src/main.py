import os
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from google import genai

BASE_URL = "https://rust.facepunch.com"
NEWS_URL = f"{BASE_URL}/news/"

HEADERS = {
    "User-Agent": "RustNewsBot/1.0"
}

def test_gemini():

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError("No se encontró GEMINI_API_KEY.")

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents="Respondé solamente: Gemini conectado correctamente."
    )

    print("\n==============================")
    print("        GEMINI TEST")
    print("==============================")
    print(response.text)


def get_page(url):
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def get_latest_news():
    soup = get_page(NEWS_URL)

    links = []

    for link in soup.find_all("a", href=True):
        href = link["href"]

        if "/news/" in href and href != "/news/":
            full_url = urljoin(BASE_URL, href)

            if full_url not in links:
                links.append(full_url)

    if not links:
        raise RuntimeError("No se encontraron noticias en Facepunch.")

    return links[0]


def inspect_milk_section(url):
    soup = get_page(url)

    sections = soup.select(".news-section-block")

    for section in sections:

        title_element = section.select_one(".section-header .title")

        if not title_element:
            continue

        title = title_element.get_text(" ", strip=True)

        if title.lower() != "milk":
            continue

        print("\n==============================")
        print("        MILK SECTION")
        print("==============================\n")

        inner = section.select_one(".inner")

        if not inner:
            print("No se encontró .inner")
            return

        for child in inner.find_all(recursive=False):

            text = child.get_text(" ", strip=True)

            if len(text) > 300:
                text = text[:300] + "..."

            classes = " ".join(child.get("class", []))

            print(
                f"TAG: {child.name} | "
                f"CLASS: {classes} | "
                f"TEXT: {text}"
            )

        return

    raise RuntimeError("No se encontró la sección Milk.")

def parse_news(url):
    soup = get_page(url)

    result = {
        "url": url,
        "title": None,
        "date": None,
        "type": None,
        "sections": []
    }

    if soup.title:
        result["title"] = soup.title.get_text(" ", strip=True)

    tags = soup.select_one(".tags")

    if tags:
        tag_text = tags.get_text(" ", strip=True)
        parts = tag_text.split()

        if parts:
            result["date"] = " ".join(parts[:3])

        if "DEVBLOG" in tag_text:
            result["type"] = "DEVBLOG"

    sections = soup.select(".news-section-block")

    for section in sections:

        title_element = section.select_one(".section-header .title")

        if not title_element:
            continue

        title = title_element.get_text(" ", strip=True)

        if not title or title == "⠀":
            continue

        author_element = section.select_one(".section-header .author")

        author = (
            author_element.get_text(" ", strip=True)
            if author_element
            else None
        )

        content_element = section.select_one(".content")

        content = (
            content_element.get_text(" ", strip=True)
            if content_element
            else ""
        )

        images = []

        for image in section.select(".content img"):

            src = image.get("src")

            if src:
                images.append(urljoin(url, src))

        result["sections"].append({
            "title": title,
            "author": author,
            "content": content,
            "images": images
        })

    return result

def save_news(news):
    os.makedirs("data", exist_ok=True)

    with open("data/latest_news.json", "w", encoding="utf-8") as file:
        json.dump(
            news,
            file,
            indent=2,
            ensure_ascii=False
        )


def main():

    print("================================")
    print("       RUST NEWS BOT")
    print("================================")

    print("\nBuscando última noticia...")

    latest_url = get_latest_news()

    print(f"URL: {latest_url}")

    print("\nAnalizando noticia...")

    news = parse_news(latest_url)
    save_news(news)

    print("\nResultado:")

    print(json.dumps(
        news,
        indent=2,
        ensure_ascii=False
    ))
    
    test_gemini()


if __name__ == "__main__":
    main()
