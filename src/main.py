import json
import os
import time

import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin
from google import genai


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

    return BeautifulSoup(
        response.text,
        "html.parser"
    )


def get_latest_news():

    soup = get_page(NEWS_URL)

    links = []

    for link in soup.find_all("a", href=True):

        href = link["href"]

        if "/news/" in href and href != "/news/":

            full_url = urljoin(
                BASE_URL,
                href
            )

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

    sections = soup.select(
        ".news-section-block"
    )

    for section in sections:

        title_element = section.select_one(
            ".section-header .title"
        )

        if not title_element:
            continue

        title = title_element.get_text(
            " ",
            strip=True
        )

        if not title or title == "⠀":
            continue

        author_element = section.select_one(
            ".section-header .author"
        )

        author = (
            author_element.get_text(
                " ",
                strip=True
            )
            if author_element
            else None
        )

        content_element = section.select_one(
            ".content"
        )

        content = (
            content_element.get_text(
                " ",
                strip=True
            )
            if content_element
            else ""
        )

        images = []

        for image in section.select(
            ".content img"
        ):

            src = image.get("src")

            if src:
                images.append(
                    urljoin(url, src)
                )

        result["sections"].append({
            "title": title,
            "author": author,
            "content": content,
            "images": images
        })

    return result


def save_news(news):

    os.makedirs(
        "data",
        exist_ok=True
    )

    with open(
        "data/latest_news.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            news,
            file,
            indent=2,
            ensure_ascii=False
        )


def analyze_section(section, client):

    prompt = f"""
You are a Rust game content analyst.

Analyze this Rust news section and determine whether it is worth creating
content about it for the Rust community on X.

Section title:
{section["title"]}

Section author:
{section["author"]}

Section content:
{section["content"]}

Return ONLY valid JSON with this exact structure:

{{
  "title": "section title",
  "importance": 0,
  "interaction_potential": 0,
  "recommended": true,
  "content_type": "news",
  "reason": "short explanation"
}}

Rules:

- importance: integer from 1 to 10.
- interaction_potential: integer from 1 to 10.
- recommended: true if this section deserves its own X post, otherwise false.
- content_type must be one of:
  "news", "question", "debate", "fact", "curiosity"
- reason must be short.
- Focus on what is interesting to Rust players.
- Consider gameplay impact, novelty, controversy, usefulness and
  potential for player interaction.
- Do not invent information that is not present in the section.
"""

    for attempt in range(3):

        try:

            response = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=prompt
            )

            return response.text

        except Exception as error:

            print(
                f"Gemini intento {attempt + 1}/3 falló: {error}"
            )

            if attempt < 2:

                print(
                    "Esperando 10 segundos antes de reintentar..."
                )

                time.sleep(10)

            else:

                raise


def analyze_all_sections(news):

    api_key = os.environ.get(
        "GEMINI_API_KEY"
    )

    if not api_key:
        raise RuntimeError(
            "No se encontró GEMINI_API_KEY."
        )

    client = genai.Client(
        api_key=api_key
    )

    analyses = []

    total = len(news["sections"])

    print(
        f"\nSe encontraron {total} secciones."
    )

    for index, section in enumerate(
        news["sections"],
        start=1
    ):

        print(
            "\n--------------------------------"
        )

        print(
            f"Sección {index}/{total}: "
            f'{section["title"]}'
        )

        print(
            "--------------------------------"
        )

        analysis_text = analyze_section(
            section,
            client
        )

        print(
            analysis_text
        )

        try:

            analysis = json.loads(
                analysis_text
            )

        except json.JSONDecodeError:

            print(
                "ADVERTENCIA: Gemini no devolvió "
                "JSON válido para esta sección."
            )

            analysis = {
                "title": section["title"],
                "importance": 0,
                "interaction_potential": 0,
                "recommended": False,
                "content_type": "news",
                "reason": "Invalid Gemini response"
            }

        analyses.append(
            analysis
        )

    return analyses


def save_analysis(news, analyses):

    os.makedirs(
        "data",
        exist_ok=True
    )

    result = {
        "url": news["url"],
        "title": news["title"],
        "date": news["date"],
        "type": news["type"],
        "sections": analyses
    }

    with open(
        "data/news_analysis.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            result,
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

    print(
        f"URL: {latest_url}"
    )

    print("\nAnalizando noticia...")

    news = parse_news(
        latest_url
    )

    save_news(
        news
    )

    print(
        "\nNoticia guardada en "
        "data/latest_news.json"
    )

    print(
        "\nAnalizando todas las secciones..."
    )

    analyses = analyze_all_sections(
        news
    )

    save_analysis(
        news,
        analyses
    )

    print(
        "\n================================"
    )

    print(
        "      ANALISIS COMPLETADO"
    )

    print(
        "================================"
    )

    print(
        "\nAnálisis guardado en "
        "data/news_analysis.json"
    )


if __name__ == "__main__":
    main()
