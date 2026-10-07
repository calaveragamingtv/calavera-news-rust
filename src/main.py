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
        "sections": []
    }

    if soup.title:
        result["title"] = soup.title.get_text(
            " ",
            strip=True
        )

    print("\n===== ELEMENTOS CON CLASE =====\n")

    for element in soup.find_all(class_=True):
        classes = element.get("class")

        text = element.get_text(
            " ",
            strip=True
        )

        if text and len(text) < 300:
            print(
                f"TAG: {element.name} | "
                f"CLASS: {' '.join(classes)} | "
                f"TEXT: {text[:200]}"
            )

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
