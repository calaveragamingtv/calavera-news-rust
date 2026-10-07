import json
import os
import re

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from google import genai


# ============================================================
# CONFIGURATION
# ============================================================

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

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

PROMPT_DIR = os.path.join(
    BASE_DIR,
    "prompt"
)

DATA_DIR = os.path.join(
    BASE_DIR,
    "data"
)

LATEST_NEWS_FILE = os.path.join(
    DATA_DIR,
    "latest_news.json"
)

ANALYSIS_FILE = os.path.join(
    DATA_DIR,
    "news_analysis.json"
)

QUEUE_FILE = os.path.join(
    DATA_DIR,
    "content_queue.json"
)


# ============================================================
# HTTP
# ============================================================

def get_page(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    return response.text


# ============================================================
# JSON / FILES
# ============================================================

def load_json(path, default=None):

    if not os.path.exists(path):
        return default

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


def save_json(path, data):

    os.makedirs(
        os.path.dirname(path),
        exist_ok=True
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )


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


# ============================================================
# RUST NEWS
# ============================================================

def get_latest_news():

    html = get_page(NEWS_URL)

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    for link in soup.select(
        'a[href*="/news/"]'
    ):

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
        "No se pudo encontrar el último devblog."
    )


# ============================================================
# PARSE NEWS
# ============================================================

def parse_news(url):

    html = get_page(url)

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    title = None

    if soup.title:

        title = soup.title.get_text(
            strip=True
        )

    if not title:

        og_title = soup.select_one(
            'meta[property="og:title"]'
        )

        if og_title:

            title = og_title.get(
                "content"
            )

    if not title:

        h1 = soup.select_one("h1")

        if h1:

            title = h1.get_text(
                " ",
                strip=True
            )

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    date = None

    time_element = soup.select_one(
        "time"
    )

    if time_element:

        date = (
            time_element.get("datetime")
            or time_element.get_text(
                " ",
                strip=True
            )
        )

    if not date:

        for selector in [
            'meta[property="article:published_time"]',
            'meta[name="date"]',
            'meta[name="publish-date"]'
        ]:

            element = soup.select_one(
                selector
            )

            if element:

                date = element.get(
                    "content"
                )

                if date:
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
                page_text
            )

            if match:

                date = match.group(0)

                break

    if not date:

        for pattern in [
            r"\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b",
            r"\b\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\b",
            r"\b[A-Za-z]+\s+\d{1,2},\s+\d{4}\b"
        ]:

            match = re.search(
                pattern,
                html
            )

            if match:

                date = match.group(0)

                break

    # --------------------------------------------------------
    # TYPE
    # --------------------------------------------------------

    article_type = None

    for element in soup.find_all("a"):

        text = element.get_text(
            " ",
            strip=True
        ).upper()

        if text == "DEVBLOG":

            article_type = "DEVBLOG"

            break

    if not article_type:

        page_text_upper = soup.get_text(
            " ",
            strip=True
        ).upper()

        if "DEVBLOG" in page_text_upper:

            article_type = "DEVBLOG"

    # --------------------------------------------------------
    # SECTIONS
    # --------------------------------------------------------

    sections = []

    blocks = soup.select(
        ".news-section-block"
    )

    for block in blocks:

        title_element = block.select_one(
            ".section-header .title"
        )

        author_element = block.select_one(
            ".section-header .author"
        )

        content_element = block.select_one(
            ".content"
        )

        section_title = (
            title_element.get_text(
                " ",
                strip=True
            )
            if title_element
            else ""
        )

        if section_title in (
            "",
            "⠀"
        ):
            continue

        author = (
            author_element.get_text(
                " ",
                strip=True
            )
            if author_element
            else ""
        )

        content = (
            content_element.get_text(
                "\n",
                strip=True
            )
            if content_element
            else ""
        )

        images = []

        if content_element:

            for image in content_element.select(
                "img"
            ):

                src = image.get(
                    "src"
                )

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

    # --------------------------------------------------------
    # DEBUG
    # --------------------------------------------------------

    print()
    print("DEBUG metadata:")
    print(f"HTML title: {title}")
    print(f"Fecha detectada: {date}")
    print(f"Tipo detectado: {article_type}")
    print(f"Secciones encontradas: {len(sections)}")

    return {
        "url": url,
        "title": title,
        "date": date,
        "type": article_type,
        "sections": sections
    }


# ============================================================
# GEMINI ANALYSIS
# ============================================================

def analyze_all_sections(news):

    section_blocks = []

    for index, section in enumerate(
        news["sections"],
        start=1
    ):

        section_blocks.append(
            f"""
SECCIÓN {index}

Título:
{section["title"]}

Autor:
{section["author"]}

Contenido:
{section["content"]}
""".strip()
        )

    sections_text = "\n\n".join(
        section_blocks
    )

    prompt = load_prompt(
        "analyze_devblog_sections.txt"
    )

    prompt = prompt.replace(
        "{{ARTICLE_TITLE}}",
        news["title"] or ""
    )

    prompt = prompt.replace(
        "{{ARTICLE_DATE}}",
        news["date"] or ""
    )

    prompt = prompt.replace(
        "{{ARTICLE_TYPE}}",
        news["type"] or ""
    )

    prompt = prompt.replace(
        "{{SECTIONS}}",
        sections_text
    )

    api_key = os.environ.get(
        "GEMINI_API_KEY"
    )

    if not api_key:

        raise RuntimeError(
            "No existe GEMINI_API_KEY."
        )

    client = genai.Client(
        api_key=api_key
    )

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json"
        }
    )

    return json.loads(
        response.text
    )


# ============================================================
# CONTENT QUEUE
# ============================================================

def create_content_queue(
    news,
    analyses
):

    sections_by_title = {
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

        # ----------------------------------------------------
        # FILTER
        # ----------------------------------------------------

        if publication_type in (
            "skip",
            "related"
        ):
            continue

        if publication_score < MIN_PUBLICATION_SCORE:
            continue

        # ----------------------------------------------------
        # FIND ORIGINAL SECTION
        # ----------------------------------------------------

        section = sections_by_title.get(
            analysis.get("title")
        )

        if not section:
            continue

        # ----------------------------------------------------
        # CREATE ITEM
        # ----------------------------------------------------

        items.append({

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

            # ------------------------------------------------
            # PUBLICATION STATE
            # ------------------------------------------------

            "published": False,

            "published_at": None,

            "platform": None,

            "post_id": None,

            # ------------------------------------------------
            # GENERATION STATE
            # ------------------------------------------------

            "generated_text": None,

            "generated_at": None
        })

    # --------------------------------------------------------
    # SORT
    # --------------------------------------------------------

    items.sort(
        key=lambda item: (
            item["publication_score"],
            item["interaction_potential"],
            item["importance"],
            item["social_value"]
        ),
        reverse=True
    )

    # --------------------------------------------------------
    # PRIORITY
    # --------------------------------------------------------

    for index, item in enumerate(
        items,
        start=1
    ):

        item["priority"] = index

    # --------------------------------------------------------
    # QUEUE
    # --------------------------------------------------------

    queue = {

        "article": {
            "url": news["url"],
            "title": news["title"],
            "date": news["date"],
            "type": news["type"]
        },

        "general_publication": {

            "discord_posted": False,

            "discord_posted_at": None,

            "x_posted": False,

            "x_posted_at": None,

            "x_post_id": None
        },

        "selection": {

            "minimum_publication_score":
                MIN_PUBLICATION_SCORE,

            "total_sections":
                len(news["sections"]),

            "selected_sections":
                len(items)
        },

        "items": items
    }

    return queue


# ============================================================
# QUEUE MIGRATION / LOAD
# ============================================================

def load_queue():

    queue = load_json(
        QUEUE_FILE,
        default=None
    )

    if not queue:
        return None

    migrated = False

    # --------------------------------------------------------
    # GENERAL PUBLICATION
    # --------------------------------------------------------

    if "general_publication" not in queue:

        print()
        print(
            "⚠️ Cola antigua detectada."
        )

        print(
            "Migrando content_queue.json..."
        )

        queue["general_publication"] = {

            "discord_posted": False,

            "discord_posted_at": None,

            "x_posted": False,

            "x_posted_at": None,

            "x_post_id": None
        }

        migrated = True

    else:

        general = queue[
            "general_publication"
        ]

        if "discord_posted" not in general:

            general["discord_posted"] = False

            migrated = True

        if "discord_posted_at" not in general:

            general["discord_posted_at"] = None

            migrated = True

        if "x_posted" not in general:

            general["x_posted"] = False

            migrated = True

        if "x_posted_at" not in general:

            general["x_posted_at"] = None

            migrated = True

        if "x_post_id" not in general:

            general["x_post_id"] = None

            migrated = True

    # --------------------------------------------------------
    # ITEMS
    # --------------------------------------------------------

    for item in queue.get(
        "items",
        []
    ):

        if "published" not in item:

            item["published"] = False

            migrated = True

        if "published_at" not in item:

            item["published_at"] = None

            migrated = True

        if "platform" not in item:

            item["platform"] = None

            migrated = True

        if "post_id" not in item:

            item["post_id"] = None

            migrated = True

        if "generated_text" not in item:

            item["generated_text"] = None

            migrated = True

        if "generated_at" not in item:

            item["generated_at"] = None

            migrated = True

    # --------------------------------------------------------
    # SAVE MIGRATION
    # --------------------------------------------------------

    if migrated:

        save_json(
            QUEUE_FILE,
            queue
        )

        print(
            "✅ Migración completada."
        )

    return queue


# ============================================================
# ARTICLE COMPARISON
# ============================================================

def is_same_article(
    queue,
    current_url
):

    if not queue:
        return False

    article = queue.get(
        "article",
        {}
    )

    stored_url = article.get(
        "url"
    )

    return stored_url == current_url


# ============================================================
# NEXT PENDING CONTENT
# ============================================================

def get_next_pending_item(
    queue
):

    items = queue.get(
        "items",
        []
    )

    pending = [
        item
        for item in items
        if not item.get(
            "published",
            False
        )
    ]

    if not pending:
        return None

    pending.sort(
        key=lambda item: item.get(
            "priority",
            999999
        )
    )

    return pending[0]


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "========================================"
    )

    print(
        "CALAVERA RUST NEWS"
    )

    print(
        "========================================"
    )

    # --------------------------------------------------------
    # GET LATEST ARTICLE
    # --------------------------------------------------------

    current_url = get_latest_news()

    print()
    print(
        "Último artículo detectado:"
    )

    print(
        current_url
    )

    # --------------------------------------------------------
    # LOAD CURRENT QUEUE
    # --------------------------------------------------------

    queue = load_queue()

    # ========================================================
    # NEW ARTICLE
    # ========================================================

    if not is_same_article(
        queue,
        current_url
    ):

        print()
        print(
            "🆕 NUEVO PATCH DETECTADO"
        )

        print()

        # ----------------------------------------------------
        # PARSE
        # ----------------------------------------------------

        news = parse_news(
            current_url
        )

        save_json(
            LATEST_NEWS_FILE,
            news
        )

        # ----------------------------------------------------
        # GEMINI
        # ----------------------------------------------------

        print()
        print(
            "Analizando secciones con Gemini..."
        )

        analyses = analyze_all_sections(
            news
        )

        save_json(
            ANALYSIS_FILE,
            analyses
        )

        # ----------------------------------------------------
        # CREATE QUEUE
        # ----------------------------------------------------

        queue = create_content_queue(
            news,
            analyses
        )

        save_json(
            QUEUE_FILE,
            queue
        )

        # ----------------------------------------------------
        # RESULT
        # ----------------------------------------------------

        print()

        print(
            "========================================"
        )

        print(
            "NUEVO CICLO CREADO"
        )

        print(
            "========================================"
        )

        print(
            f"Patch: "
            f"{queue['article']['title']}"
        )

        print(
            f"Secciones totales: "
            f"{queue['selection']['total_sections']}"
        )

        print(
            f"Secciones seleccionadas: "
            f"{queue['selection']['selected_sections']}"
        )

        print()

        print(
            "Publicación general:"
        )

        print(
            f"Discord: "
            f"{queue['general_publication']['discord_posted']}"
        )

        print(
            f"X: "
            f"{queue['general_publication']['x_posted']}"
        )

        print()

        print(
            "⚠️ Todavía no se publica "
            "ningún contenido."
        )

        print(
            "El ciclo quedó preparado."
        )

        return

    # ========================================================
    # EXISTING ARTICLE
    # ========================================================

    print()

    print(
        "♻️ PATCH ACTUAL YA ESTÁ EN COLA"
    )

    print(
        f"Patch: "
        f"{queue['article']['title']}"
    )

    # --------------------------------------------------------
    # GENERAL PUBLICATION STATE
    # --------------------------------------------------------

    general = queue.get(
        "general_publication",
        {}
    )

    print()

    print(
        f"Discord general publicado: "
        f"{general.get('discord_posted', False)}"
    )

    print(
        f"X general publicado: "
        f"{general.get('x_posted', False)}"
    )

    # --------------------------------------------------------
    # NEXT ITEM
    # --------------------------------------------------------

    next_item = get_next_pending_item(
        queue
    )

    # ========================================================
    # CYCLE COMPLETED
    # ========================================================

    if next_item is None:

        print()

        print(
            "========================================"
        )

        print(
            "CICLO COMPLETADO"
        )

        print(
            "========================================"
        )

        print(
            "No quedan secciones pendientes "
            "para este patch."
        )

        return

    # ========================================================
    # NEXT CONTENT
    # ========================================================

    print()

    print(
        "========================================"
    )

    print(
        "SIGUIENTE CONTENIDO PENDIENTE"
    )

    print(
        "========================================"
    )

    print(
        f"Priority: "
        f"{next_item['priority']}"
    )

    print(
        f"Título: "
        f"{next_item['title']}"
    )

    print(
        f"Score: "
        f"{next_item['publication_score']}"
    )

    print(
        f"Tipo: "
        f"{next_item['content_type']}"
    )

    print(
        f"Publicado: "
        f"{next_item['published']}"
    )

    print()

    print(
        "⚠️ Todavía NO se marca como publicado."
    )

    print(
        "La publicación real se agregará "
        "en el siguiente paso."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
