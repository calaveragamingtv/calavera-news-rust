import json
import os
import re

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from google import genai


BASE_URL = "https://rust.facepunch.com"
NEWS_URL = f"{BASE_URL}/news/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    )
}

GEMINI_MODEL = "gemini-3.5-flash-lite"

MIN_PUBLICATION_SCORE = 75

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROMPT_DIR = os.path.join(
    BASE_DIR,
    "prompt"
)

DATA_DIR = os.path.join(
    BASE_DIR,
    "data"
)


# =========================================================
# HTTP
# =========================================================

def get_page(url):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    return response.text


# =========================================================
# PROMPTS
# =========================================================

def load_prompt(filename):

    path = os.path.join(
        PROMPT_DIR,
        filename
    )

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:

        return file.read()


# =========================================================
# FIND LATEST NEWS
# =========================================================

def get_latest_news():

    html = get_page(NEWS_URL)

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    for link in soup.select('a[href*="/news/"]'):

        href = link.get("href")

        if not href:
            continue

        if href == "/news/":
            continue

        if not href.startswith("/news/"):
            continue

        url = urljoin(
            BASE_URL,
            href
        )

        return url

    raise RuntimeError(
        "No se encontró ningún artículo de Rust."
    )


# =========================================================
# PARSE NEWS
# =========================================================

def parse_news(url):

    html = get_page(url)

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    print("DEBUG metadata:")

    print(
        "HTML title:",
        soup.title.get_text(
            " ",
            strip=True
        )
        if soup.title
        else "NO ENCONTRADO"
    )

    print(
        "h1:",
        soup.find("h1").get_text(
            " ",
            strip=True
        )
        if soup.find("h1")
        else "NO ENCONTRADO"
    )

    print(
        "time:",
        soup.find("time").get_text(
            " ",
            strip=True
        )
        if soup.find("time")
        else "NO ENCONTRADO"
    )

    print(
        "DEVBLOG links:",
        len(
            [
                a
                for a in soup.find_all("a")
                if a.get_text(
                    " ",
                    strip=True
                ).upper() == "DEVBLOG"
            ]
        )
    )

    # -----------------------------------------------------
    # TITLE
    # -----------------------------------------------------

    title = ""

    if soup.title:

        title = soup.title.get_text(
            " ",
            strip=True
        )

    if not title:

        og_title = soup.select_one(
            'meta[property="og:title"]'
        )

        if og_title:

            title = og_title.get(
                "content",
                ""
            ).strip()

    if not title:

        h1 = soup.find("h1")

        if h1:

            title = h1.get_text(
                " ",
                strip=True
            )

    # -----------------------------------------------------
    # DATE
    # -----------------------------------------------------

    date = ""

    time_element = soup.find("time")

    if time_element:

        date = (
            time_element.get("datetime")
            or time_element.get_text(
                " ",
                strip=True
            )
        )

    if not date:

        date_selectors = [
            'meta[property="article:published_time"]',
            'meta[property="article:modified_time"]',
            'meta[name="date"]',
            'meta[name="pubdate"]',
            'meta[name="publishdate"]',
            'meta[itemprop="datePublished"]',
            'meta[itemprop="dateCreated"]'
        ]

        for selector in date_selectors:

            element = soup.select_one(
                selector
            )

            if element:

                value = (
                    element.get("content")
                    or element.get("datetime")
                    or ""
                ).strip()

                if value:

                    date = value

                    break

    if not date:

        page_text = soup.get_text(
            " ",
            strip=True
        )

        date_patterns = [
            r"\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b",
            r"\b\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\b",
            r"\b[A-Za-z]+\s+\d{1,2},\s+\d{4}\b"
        ]

        for pattern in date_patterns:

            match = re.search(
                pattern,
                page_text,
                re.IGNORECASE
            )

            if match:

                date = match.group(0)

                break

    if not date:

        date_patterns = [
            r"\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b",
            r"\b\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\b",
            r"\b[A-Za-z]+\s+\d{1,2},\s+\d{4}\b"
        ]

        for pattern in date_patterns:

            match = re.search(
                pattern,
                html,
                re.IGNORECASE
            )

            if match:

                date = match.group(0)

                break

    # -----------------------------------------------------
    # TYPE
    # -----------------------------------------------------

    news_type = ""

    for element in soup.find_all("a"):

        text = element.get_text(
            " ",
            strip=True
        )

        if text.upper() == "DEVBLOG":

            news_type = "DEVBLOG"

            break

    if not news_type:

        page_text = soup.get_text(
            " ",
            strip=True
        )

        if "DEVBLOG" in page_text.upper():

            news_type = "DEVBLOG"

    # -----------------------------------------------------
    # SECTIONS
    # -----------------------------------------------------

    sections = []

    section_blocks = soup.select(
        ".news-section-block"
    )

    for block in section_blocks:

        title_element = block.select_one(
            ".section-header .title"
        )

        if not title_element:
            continue

        section_title = title_element.get_text(
            " ",
            strip=True
        )

        if not section_title:
            continue

        if section_title == "⠀":
            continue

        author_element = block.select_one(
            ".section-header .author"
        )

        author = ""

        if author_element:

            author = author_element.get_text(
                " ",
                strip=True
            )

        content_element = block.select_one(
            ".content"
        )

        content = ""

        if content_element:

            content = content_element.get_text(
                "\n",
                strip=True
            )

        images = []

        if content_element:

            for img in content_element.select("img"):

                src = img.get("src")

                if src:

                    images.append(
                        urljoin(
                            BASE_URL,
                            src
                        )
                    )

        sections.append({
            "title": section_title,
            "author": author,
            "content": content,
            "images": images
        })

    print(
        "Secciones encontradas:",
        len(sections)
    )

    print(
        "Título detectado:",
        title
    )

    print(
        "Fecha detectada:",
        date
    )

    print(
        "Tipo detectado:",
        news_type
    )

    return {
        "url": url,
        "title": title,
        "date": date,
        "type": news_type,
        "sections": sections
    }


# =========================================================
# SAVE NEWS
# =========================================================

def save_news(news):

    path = os.path.join(
        DATA_DIR,
        "latest_news.json"
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            news,
            file,
            ensure_ascii=False,
            indent=2
        )


# =========================================================
# GEMINI ANALYSIS
# =========================================================

def analyze_all_sections(news):

    print(
        "Analizando secciones con Gemini..."
    )

    sections = news["sections"]

    sections_text = []

    for index, section in enumerate(
        sections,
        start=1
    ):

        sections_text.append(
            f"""
SECCIÓN {index}

Título:
{section["title"]}

Autor:
{section["author"]}

Contenido:
{section["content"]}
"""
        )

    article_sections = "\n".join(
        sections_text
    )

    prompt_template = load_prompt(
        "analyze_devblog_sections.txt"
    )

    prompt = (
        prompt_template
        .replace(
            "{{ARTICLE_TITLE}}",
            news["title"]
        )
        .replace(
            "{{ARTICLE_DATE}}",
            news["date"]
        )
        .replace(
            "{{ARTICLE_TYPE}}",
            news["type"]
        )
        .replace(
            "{{SECTIONS}}",
            article_sections
        )
    )

    client = genai.Client(
        api_key=os.environ.get(
            "GEMINI_API_KEY"
        )
    )

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json"
        }
    )

    try:

        analyses = json.loads(
            response.text
        )

    except json.JSONDecodeError:

        print(
            "ERROR: Gemini no devolvió JSON válido."
        )

        print(response.text)

        raise

    return analyses


# =========================================================
# SAVE ANALYSIS
# =========================================================

def save_analysis(
    news,
    analyses
):

    output = {
        "article": {
            "url": news["url"],
            "title": news["title"],
            "date": news["date"],
            "type": news["type"]
        },
        "analyses": analyses
    }

    path = os.path.join(
        DATA_DIR,
        "news_analysis.json"
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            output,
            file,
            ensure_ascii=False,
            indent=2
        )


# =========================================================
# CREATE CONTENT QUEUE
# =========================================================

def create_content_queue(
    news,
    analyses
):

    print(
        "Creando content queue..."
    )

    section_map = {
        section["title"]: section
        for section in news["sections"]
    }

    items = []

    for analysis in analyses:

        publication_type = analysis.get(
            "publication_type",
            "skip"
        )

        publication_score = analysis.get(
            "publication_score",
            0
        )

        if publication_type in (
            "skip",
            "related"
        ):
            continue

        if publication_score < MIN_PUBLICATION_SCORE:
            continue

        section = section_map.get(
            analysis["title"]
        )

        if not section:
            continue

        item = {
            "article_url": news["url"],
            "article_title": news["title"],
            "article_date": news["date"],
            "article_type": news["type"],

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

            "social_value": analysis.get(
                "social_value",
                0
            ),

            "publication_score": publication_score,

            "recommended": analysis.get(
                "recommended",
                False
            ),

            "publication_type": publication_type,

            "content_type": analysis.get(
                "content_type",
                "news"
            ),

            "reason": analysis.get(
                "reason",
                ""
            ),

            "published": False,
            "published_at": None,
            "platform": None
        }

        items.append(item)

    # -----------------------------------------------------
    # SORT
    # -----------------------------------------------------

    items.sort(
        key=lambda item: (
            item["publication_score"],
            item["interaction_potential"],
            item["importance"]
        ),
        reverse=True
    )

    # -----------------------------------------------------
    # PRIORITY
    # -----------------------------------------------------

    for index, item in enumerate(
        items,
        start=1
    ):

        item["priority"] = index

    queue = {
        "article": {
            "url": news["url"],
            "title": news["title"],
            "date": news["date"],
            "type": news["type"]
        },

        "selection": {
            "minimum_publication_score": MIN_PUBLICATION_SCORE,
            "total_sections": len(
                news["sections"]
            ),
            "selected_sections": len(
                items
            )
        },

        "items": items
    }

    path = os.path.join(
        DATA_DIR,
        "content_queue.json"
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            queue,
            file,
            ensure_ascii=False,
            indent=2
        )

    print(
        "Contenido seleccionado:",
        len(items)
    )

    for item in items:

        print(
            f'{item["priority"]}. '
            f'{item["title"]} '
            f'({item["publication_score"]})'
        )


# =========================================================
# MAIN
# =========================================================

def main():

    print("Buscando último Rust Devblog...")

    latest_url = get_latest_news()

    print(
        "Último artículo:",
        latest_url
    )

    news = parse_news(
        latest_url
    )

    save_news(
        news
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

    print(
        "Proceso terminado."
    )


if __name__ == "__main__":
    main()
