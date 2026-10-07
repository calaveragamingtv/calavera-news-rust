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
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


def get_latest_news():
    html = get_page(NEWS_URL)
    soup = BeautifulSoup(html, "html.parser")

    link = soup.select_one("a.news-item")

    if not link:
        raise Exception("No se pudo encontrar la última noticia.")

    href = link.get("href")

    if not href:
        raise Exception("La noticia no tiene URL.")

    return urljoin(BASE_URL, href)


def parse_news(url):
    html = get_page(url)
    soup = BeautifulSoup(html, "html.parser")

    title_element = soup.select_one("h1")
    title = title_element.get_text(" ", strip=True) if title_element else ""

    date = ""
    date_element = soup.select_one("time")

    if date_element:
        date = date_element.get_text(" ", strip=True)

    type_element = soup.select_one(".news-type")

    news_type = (
        type_element.get_text(" ", strip=True)
        if type_element
        else "DEVBLOG"
    )

    sections = []

    for block in soup.select(".news-section-block"):

        header = block.select_one(".section-header")

        if not header:
            continue

        title_element = header.select_one(".title")

        if not title_element:
            continue

        section_title = title_element.get_text(" ", strip=True)

        if not section_title or section_title == "⠀":
            continue

        author_element = header.select_one(".author")

        author = (
            author_element.get_text(" ", strip=True)
            if author_element
            else ""
        )

        content_element = block.select_one(".content")

        if not content_element:
            continue

        content = content_element.get_text(" ", strip=True)

        images = []

        for image in content_element.select("img"):
            src = image.get("src")

            if src:
                images.append(urljoin(BASE_URL, src))

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

    print("Noticia guardada en data/latest_news.json")


def analyze_all_sections(news):

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise Exception("No se encontró GEMINI_API_KEY.")

    client = genai.Client(api_key=api_key)

    sections_text = ""

    for index, section in enumerate(news["sections"], start=1):

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
You are analyzing a Rust Facepunch devblog for a Spanish-speaking Rust content creator.

ARTICLE:
{news["title"]}

DATE:
{news["date"]}

TYPE:
{news["type"]}

Your task is to analyze ALL sections and determine which ones deserve
individual social media content.

IMPORTANT LANGUAGE RULE:

The ORIGINAL section titles and source information must remain unchanged.

However, ALL AI-GENERATED TEXT must be written in natural Latin American Spanish.

This includes:
- reasons
- explanations
- future tweet ideas
- future Discord content
- any other generated text

DO NOT generate final social media text in English.

Use natural Latin American Spanish, not literal or robotic translations.

Rust item names, monument names, mechanics, systems and official terminology
may remain in English when that is the official name used by the game.

For every section return exactly one analysis object.

Return ONLY valid JSON.

Do not use markdown.
Do not use ```json.
Do not add explanations outside the JSON.

The JSON must have exactly this structure:

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

1. "title"
   - Must be EXACTLY the original section title.
   - Do not translate it.

2. "importance"
   - Integer from 1 to 10.
   - Measures how important the information is for Rust players.

3. "interaction_potential"
   - Integer from 1 to 10.
   - Measures how likely the topic is to generate comments, discussion,
     reactions or interest on social media.

4. "recommended"
   - true only if the section deserves individual social media content.
   - false for minor, repetitive, purely technical or low-interest information.

5. "priority"
   - Integer starting at 1.
   - 1 is the MOST important section to publish.
   - Higher numbers mean lower priority.
   - Recommended sections should receive the highest priorities.
   - Non-recommended sections should receive the lowest priorities.
   - Every section must have a unique priority.

6. "publication_type"
   Must be exactly one of:
   - "standalone"
   - "related"
   - "skip"

   "standalone":
   The section deserves its own independent social media post.

   "related":
   The section is interesting but is strongly related to another major section
   and may work better combined with it rather than as an independent post.

   "skip":
   The section should not generate social media content.

7. "content_type"
   Must be exactly one of:
   - "news"
   - "question"
   - "debate"
   - "fact"
   - "curiosity"

8. "reason"
   - Short explanation in natural Latin American Spanish.
   - Explain why the section does or does not deserve content.

IMPORTANT:

Compare the sections against each other.

Do NOT mark everything as recommended.

The goal is to identify the strongest content from the entire article.

Prioritize:

- major gameplay changes
- new mechanics
- important balance changes
- major changes to the Rust meta
- controversial changes
- useful information for players
- surprising mechanics
- information that creates discussion
- information that can generate strong Rust community reactions

Normally do NOT recommend:

- minor bug fixes
- small technical optimizations
- cosmetic-only changes
- minor UI changes
- routine backend changes
- repetitive information
- low-impact details

Avoid creating multiple independent posts about essentially the same topic.

For example, if several sections explain different aspects of one major feature,
the main feature can be "standalone" while related details can be "related".

The eventual social media strategy is:

- one strong piece of content at a time
- prioritize the most interesting topics first
- avoid repetitive posts
- eventually publish remaining worthwhile sections on subsequent days
- stop when there is no worthwhile content remaining

Here are ALL sections:

{sections_text}
"""

    max_retries = 3

    for attempt in range(1, max_retries + 1):

        try:

            print("Enviando todas las secciones a Gemini...")

            response = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=prompt
            )

            print("Respuesta recibida de Gemini.")

            result = json.loads(response.text)

            analyses = result.get("sections")

            if not isinstance(analyses, list):
                raise Exception(
                    "Gemini no devolvió una lista válida de secciones."
                )

            if len(analyses) != len(news["sections"]):
                raise Exception(
                    f"Gemini devolvió {len(analyses)} análisis "
                    f"pero deberían ser {len(news['sections'])}."
                )

            return analyses

        except Exception as error:

            print(f"Error con Gemini: {error}")

            if attempt < max_retries:
                print("Esperando 30 segundos antes de reintentar...")
                time.sleep(30)
            else:
                raise


def save_analysis(news, analyses):

    os.makedirs("data", exist_ok=True)

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

    print("Análisis guardado en data/news_analysis.json")


def create_content_queue(news, analyses):

    queue = []

    for analysis in analyses:

        if not analysis.get("recommended"):
            continue

        if analysis.get("publication_type") == "skip":
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
            "importance": analysis["importance"],
            "interaction_potential": analysis["interaction_potential"],
            "priority": analysis["priority"],
            "publication_type": analysis["publication_type"],
            "content_type": analysis["content_type"],
            "published": False
        })

    queue.sort(key=lambda item: item["priority"])

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

    print("Cola guardada en data/content_queue.json")
    print(f"Se encontraron {len(queue)} contenidos recomendados.")


def main():

    print("================================")
    print("       RUST NEWS BOT")
    print("================================")

    print("Buscando última noticia...")

    latest_url = get_latest_news()

    print(f"URL: {latest_url}")

    print("Analizando noticia...")

    news = parse_news(latest_url)

    save_news(news)

    print(
        f"Se encontraron {len(news['sections'])} secciones."
    )

    print("Analizando todas las secciones con Gemini...")

    analyses = analyze_all_sections(news)

    save_analysis(news, analyses)

    create_content_queue(news, analyses)

    print("================================")
    print("      ANALISIS COMPLETADO")
    print("================================")

    print(
        f"Se analizaron {len(analyses)} secciones."
    )


if __name__ == "__main__":
    main()
