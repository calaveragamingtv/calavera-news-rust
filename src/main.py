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
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def get_latest_news():
    soup = get_page(NEWS_URL)

    # Por ahora buscamos los enlaces de noticias.
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


def parse_news(url):
    soup = get_page(url)

    result = {
        "url": url,
        "title": None,
        "sections": []
    }

    if soup.title:
        result["title"] = soup.title.get_text(strip=True)

    # Mostrar los headings para descubrir
    # cómo Facepunch estructura las secciones.
    for heading in soup.find_all(["h1", "h2", "h3", "h4"]):
        text = heading.get_text(" ", strip=True)

        if text:
            result["sections"].append({
                "title": text
            })

    return result


def main():
    print("Buscando última noticia de Rust...")

    latest_url = get_latest_news()

    print(f"Última noticia encontrada:")
    print(latest_url)

    print("\nAnalizando noticia...")

    news = parse_news(latest_url)

    print(json.dumps(news, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
