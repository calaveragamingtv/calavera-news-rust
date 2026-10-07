import json
import os
import time

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from google import genai


BASE_URL = "https://rust.facepunch.com"
NEWS_URL = "https://rust.facepunch.com/news/"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def get_page(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    return response.text


def get_latest_news():
    html = get_page(NEWS_URL)

    soup = BeautifulSoup(html, "html.parser")

    # Facepunch muestra las noticias dentro de los bloques
    # de noticias de la página principal.
    news_links = soup.select("a[href*='/news/']")

    for link in news_links:

        href = link.get("href")

        if not href:
            continue

        href = href.strip()

        if href == "/news/":
            continue

        if not href.startswith("/news/"):
            continue

        # Evitamos URLs que no sean artículos concretos.
        if href.count("/") < 2:
            continue

        return urljoin(BASE_URL, href)

    raise Exception("No se pudo encontrar la última noticia.")


def parse_news(url):
    html = get_page(url)

    soup = BeautifulSoup(html, "html.parser")

    title = ""

    title_element = soup.select_one("h1")

    if title_element:
        title = title_element.get_text(" ", strip=True)

    date = ""

    date_element = soup.select_one("time")

    if date_element:
        date = date_element.get_text(" ", strip=True)

    news_type = "DEVBLOG"

    # Buscar el tipo de noticia si existe.
    type_candidates = soup.select(
        ".news-type, .type, .news-header .type"
    )

    for element in type_candidates:

        value = element.get_text(" ", strip=True)

        if value:
            news_type = value
            break

    sections = []

    for block in soup.select(".news-section-block"):

        header = block.select_one(".section-header")

        if not header:
            continue

        title_element = header.select_one(".title")

        if not title_element:
            continue

        section_title = title_element.get_text(
            " ",
            strip=True
        )

        # Facepunch puede tener títulos vacíos o caracteres
        # especiales utilizados como separadores.
        if not section_title:
            continue

        if section_title == "⠀":
            continue

        author_element = header.select_one(".author")

        author = ""

        if author_element:
            author = author_element.get_text(
                " ",
                strip=True
            )

        content_element = block.select_one(".content")

        if not content_element:
            continue

        content = content_element.get_text(
            " ",
            strip=True
        )

        images = []

        for image in content_element.select("img"):

            src = image.get("src")

            if not src:
                continue

            images.append(
                urljoin(BASE_URL, src)
            )

        sections.append({
            "title": section_title,
            "author": author,
            "content": content,
            "images": images
        })

    return {
        "url": url,
        "title": title,
        "date": date,
        "type": news_type,
        "sections": sections
    }


def save_news(news):

    os.makedirs("data", exist_ok=True)

    with open(
        "data/latest_news.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            news,
            file,
            ensure_ascii=False,
            indent=2
        )

    print(
        "Noticia guardada en data/latest_news.json"
    )


def analyze_all_sections(news):

    api_key = os.environ.get(
        "GEMINI_API_KEY"
    )

    if not api_key:
        raise Exception(
            "No se encontró GEMINI_API_KEY."
        )

    client = genai.Client(
        api_key=api_key
    )

    sections_text = ""

    for index, section in enumerate(
        news["sections"],
        start=1
    ):

        sections_text += f"""
SECTION {index}

Title:
{section["title"]}

Author:
{section["author"]}

Content:
{section["content"]}

---
"""

    prompt = f"""
You are analyzing a Rust Facepunch devblog for a
Spanish-speaking Rust content creator.

ARTICLE:
{news["title"]}

DATE:
{news["date"]}

TYPE:
{news["type"]}

Your task is to analyze ALL sections and determine which
ones deserve individual social media content.

IMPORTANT LANGUAGE RULE:

The ORIGINAL section titles and source information must
remain unchanged.

ALL AI-GENERATED TEXT MUST BE IN NATURAL LATIN AMERICAN SPANISH.

This includes:
- reasons
- explanations
- future tweet ideas
- Discord content
- any other generated text

DO NOT generate final social media text in English.

Do not use robotic or literal translations.

Use natural Latin American Spanish suitable for a Rust
gaming community.

Rust item names, monument names, mechanics, systems and
official terminology may remain in English when that is
the official name used by the game.

Return ONLY valid JSON.

Do not use markdown.
Do not use ```json.
Do not add explanations outside the JSON.

Return exactly this structure:

{{
  "sections": [
    {{
      "title": "original section title",
      "importance": 0,
      "interaction_potential": 0,
      "recommended": true,
      "priority": 0,
      "publication_type": "standalone",
      "content_type": "news",
      "reason": "explicación breve en español latino"
    }}
  ]
}}

RULES:

1. title

Must be EXACTLY the original section title.

Do not translate it.

2. importance

Integer from 1 to 10.

Measures how important the information is for Rust players.

3. interaction_potential

Integer from 1 to 10.

Measures how likely the topic is to generate comments,
discussion, reactions or interest on social media.

4. recommended

true only if the section deserves individual social
media content.

false for minor, repetitive, purely technical or
low-interest information.

Do NOT mark everything as recommended.

5. priority

Every section must receive a unique integer priority.

1 = highest priority.

Higher numbers = lower priority.

The strongest and most interesting topics must receive
the lowest priority numbers.

6. publication_type

Must be exactly one of:

"standalone"
"related"
"skip"

standalone:
The section deserves its own independent social media post.

related:
The section is interesting but is strongly related to
another major section and may work better combined with it.

skip:
The section should not generate social media content.

7. content_type

Must be exactly one of:

"news"
"question"
"debate"
"fact"
"curiosity"

8. reason

Short explanation in natural Latin American Spanish.

Explain why the section does or does not deserve content.

Compare all sections against each other.

Prioritize:

- major gameplay changes
- new mechanics
- important balance changes
- major changes to the Rust meta
- controversial changes
- useful information for players
- surprising mechanics
- discussion potential
- topics that can generate strong Rust community reactions

Normally do NOT recommend:

- minor bug fixes
- small technical optimizations
- cosmetic-only changes
- minor UI changes
- routine backend changes
- repetitive information
- low-impact details

Avoid creating multiple independent posts about
essentially the same topic.

If several sections describe different aspects of one
major feature, the main feature can be "standalone"
while secondary details can be "related".

The eventual social media strategy is:

- publish the strongest content first
- one strong piece of content at a time
- avoid repetitive posts
- use remaining worthwhile sections on subsequent days
- stop when there is no worthwhile content remaining

Here are ALL sections:

{sections_text}
"""

    max_retries = 3

    for attempt in range(
        1,
        max_retries + 1
    ):

        try:

            print(
                "Enviando todas las secciones a Gemini..."
            )

            response = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=prompt
            )

            print(
                "Respuesta recibida de Gemini."
            )

            result = json.loads(
                response.text
            )

            analyses = result.get(
                "sections"
            )

            if not isinstance(
                analyses,
                list
            ):
                raise Exception(
                    "Gemini no devolvió una lista válida de secciones."
                )

            if len(analyses) != len(
                news["sections"]
            ):
                raise Exception(
                    f"Gemini devolvió {len(analyses)} "
                    f"análisis pero deberían ser "
                    f"{len(news['sections'])}."
                )

            return analyses

        except Exception as error:

            print(
                f"Error con Gemini: {error}"
            )

            if attempt < max_retries:

                print(
                    "Esperando 30 segundos antes de reintentar..."
                )

                time.sleep(30)

            else:
                raise


def save_analysis(
    news,
    analyses
):

    os.makedirs(
        "data",
        exist_ok=True
    )

    analysis_data = {
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
            analysis_data,
            file,
            ensure_ascii=False,
            indent=2
        )

    print(
        "Análisis guardado en data/news_analysis.json"
    )


def create_content_queue(
    news,
    analyses
):

    queue = []

    for analysis in analyses:

        if not analysis.get(
            "recommended",
            False
        ):
            continue

        publication_type = analysis.get(
            "publication_type",
            "skip"
        )

        if publication_type == "skip":
            continue

        section = next(
            (
                item
                for item in news["sections"]
                if item["title"] == analysis["title"]
            ),
            None
        )

        if not section:
            continue

        queue.append({
            "title": section["title"],
            "author": section["author"],
            "content": section["content"],
            "images": section["images"],
            "importance": analysis.get(
                "importance",
                0
            ),
            "interaction_potential": analysis.get(
                "interaction_potential",
                0
            ),
            "priority": analysis.get(
                "priority",
                999
            ),
            "publication_type": publication_type,
            "content_type": analysis.get(
                "content_type",
                "news"
            ),
            "published": False
        })

    queue.sort(
        key=lambda item: item["priority"]
    )

    queue_data = {
        "url": news["url"],
        "title": news["title"],
        "date": news["date"],
        "status": "pending",
        "sections": queue
    }

    with open(
        "data/content_queue.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            queue_data,
            file,
            ensure_ascii=False,
            indent=2
        )

    print(
        "Cola guardada en data/content_queue.json"
    )

    print(
        f"Se encontraron {len(queue)} "
        f"contenidos recomendados."
    )


def main():

    print("================================")
    print("       RUST NEWS BOT")
    print("================================")

    print(
        "Buscando última noticia..."
    )

    latest_url = get_latest_news()

    print(
        f"URL: {latest_url}"
    )

    print(
        "Analizando noticia..."
    )

    news = parse_news(
        latest_url
    )

    save_news(
        news
    )

    print(
        f"Se encontraron "
        f"{len(news['sections'])} secciones."
    )

    print(
        "Analizando todas las secciones con Gemini..."
    )

    analyses = analyze_all_sections(
        news
    )

    save_analysis(
        news,
        analyses
    )

    create_content_queue(
        news,
        analyses
    )

    print("================================")
    print("      ANALISIS COMPLETADO")
    print("================================")

    print(
        f"Se analizaron "
        f"{len(analyses)} secciones."
    )


if __name__ == "__main__":
    main()
