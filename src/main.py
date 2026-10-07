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


def main():

    print("================================")
    print("       RUST NEWS BOT")
    print("================================")

    print("\nBuscando última noticia...")

    latest_url = get_latest_news()

    print(f"URL: {latest_url}")

    print("\nAnalizando sección Milk...")

    inspect_milk_section(latest_url)


if __name__ == "__main__":
    main()
