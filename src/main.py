import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://rust.facepunch.com"
NEWS_URL = f"{BASE_URL}/news/"

HEADERS = {
    "User-Agent": "RustNewsBot/1.0"
}


def get_page(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

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
        raise RuntimeError(
            "No se encontraron noticias en Facepunch."
        )

    return links[0]


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
        result["title"] = soup.title.get_text(
            " ",
            strip=True
        )

    # Información general de la noticia
    tags = soup.select_one(".tags")

    if tags:
        tag_text = tags.get_text(
            " ",
            strip=True
        )

        parts = tag_text.split()

        if parts:
            result["date"] = " ".join(parts[:3])

        if "DEVBLOG" in tag_text:
            result["type"] = "DEVBLOG"

    # Secciones reales de Facepunch
    sections = soup.select(".news-section-block")

    for section in sections:

        title_element = section.select_one(
            ".section-header .title"
        )

        author_element = section.select_one(
            ".section-header .author"
        )

        if not title_element:
            continue

        title = title_element.get_text(
            " ",
            strip=True
        )

        author = None

        if author_element:
            author = author_element.get_text(
                " ",
                strip=True
            )

        result["sections"].append({
            "title": title,
            "author": author
        })

    return result


def main():
    print("================================")
    print("       RUST NEWS BOT")
    print("================================")

    print("\nBuscando última noticia...")

    latest_url = get_latest_news()

    print(f"URL: {latest_url}")

    print("\nAnalizando noticia...")

    news = parse_news(latest_url)

    print("\nResultado:")
    print(
        json.dumps(
            news,
            indent=2,
            ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
