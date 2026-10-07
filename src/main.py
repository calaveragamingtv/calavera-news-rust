import os
import json
import re
import requests

from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from google import genai


# ============================================================
# CONFIGURATION
# ============================================================

BASE_URL = "https://rust.facepunch.com/news/"
NEWS_BASE_URL = "https://rust.facepunch.com"

GEMINI_MODEL = "gemini-3.5-flash-lite"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
BUFFER_API_KEY = os.getenv("BUFFER_API_KEY")
BUFFER_CHANNEL_ID = os.getenv("BUFFER_CHANNEL_ID")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(ROOT_DIR, "data")
PROMPT_DIR = os.path.join(ROOT_DIR, "prompt")

LATEST_NEWS_FILE = os.path.join(DATA_DIR, "latest_news.json")
NEWS_ANALYSIS_FILE = os.path.join(DATA_DIR, "news_analysis.json")
QUEUE_FILE = os.path.join(DATA_DIR, "content_queue.json")

ANALYZE_PROMPT_FILE = os.path.join(
    PROMPT_DIR,
    "analyze_devblog_sections.txt"
)

X_POST_PROMPT_FILE = os.path.join(
    PROMPT_DIR,
    "generate_x_post.txt"
)

GENERAL_ANNOUNCEMENT_PROMPT_FILE = os.path.join(
    PROMPT_DIR,
    "generate_general_announcement.txt"
)

MINIMUM_PUBLICATION_SCORE = 75


# ============================================================
# GEMINI
# ============================================================

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY no está configurada.")

client = genai.Client(api_key=GEMINI_API_KEY)


# ============================================================
# GENERIC HELPERS
# ============================================================

def load_json(path, default=None):
    if not os.path.exists(path):
        return default

    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as exc:
        print(f"ERROR leyendo JSON {path}: {exc}")
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )


def load_prompt(path):
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No existe el prompt: {path}"
        )

    with open(path, "r", encoding="utf-8") as file:
        return file.read()


def clean_text(text):
    if not text:
        return ""

    return re.sub(
        r"\s+",
        " ",
        text
    ).strip()


def parse_json_response(text):
    """
    Intenta convertir una respuesta de Gemini en JSON.

    Soporta respuestas que accidentalmente vienen dentro
    de ```json ... ```.
    """

    if not text:
        raise ValueError("Gemini devolvió una respuesta vacía.")

    text = text.strip()

    if text.startswith("```"):
        text = re.sub(
            r"^```(?:json)?\s*",
            "",
            text,
            flags=re.IGNORECASE
        )

        text = re.sub(
            r"\s*```$",
            "",
            text
        )

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Intento adicional: buscar el primer objeto JSON.
    object_match = re.search(
        r"\{.*\}",
        text,
        flags=re.DOTALL
    )

    if object_match:
        return json.loads(
            object_match.group(0)
        )

    # Intento adicional: buscar un array JSON.
    array_match = re.search(
        r"\[.*\]",
        text,
        flags=re.DOTALL
    )

    if array_match:
        return json.loads(
            array_match.group(0)
        )

    raise ValueError(
        "No se pudo interpretar la respuesta de Gemini como JSON.\n"
        f"Respuesta:\n{text}"
    )


# ============================================================
# RUST NEWS SCRAPER
# ============================================================

def get_latest_news():
    print("Buscando último Rust News...")

    response = requests.get(
        BASE_URL,
        timeout=30,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; CalaveraGamingTV Rust News Bot)"
            )
        }
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
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
        "No se encontró el último artículo de Rust."
    )


def extract_article_metadata(soup, html):
    """
    Obtiene título, fecha y tipo del artículo.

    Facepunch no siempre expone estos datos con el mismo
    selector, por eso tenemos varios fallbacks.
    """

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    title = None

    h1 = soup.find("h1")

    if h1:
        title = clean_text(
            h1.get_text(" ", strip=True)
        )

    if not title:
        og_title = soup.find(
            "meta",
            property="og:title"
        )

        if og_title:
            title = clean_text(
                og_title.get("content")
            )

    if not title and soup.title:
        title = clean_text(
            soup.title.get_text()
        )

        title = re.sub(
            r"\s*-\s*News\s*-\s*Rust\s*$",
            "",
            title,
            flags=re.IGNORECASE
        )

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    date = None

    time_element = soup.find("time")

    if time_element:
        date = (
            time_element.get("datetime")
            or time_element.get_text(" ", strip=True)
        )

    if not date:
        text_content = soup.get_text(
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
                text_content
            )

            if match:
                date = match.group(0)
                break

    # --------------------------------------------------------
    # TYPE
    # --------------------------------------------------------

    article_type = None

    page_text_upper = soup.get_text(
        " ",
        strip=True
    ).upper()

    if "DEVBLOG" in page_text_upper:
        article_type = "DEVBLOG"

    elif "COMMUNITY" in page_text_upper:
        article_type = "COMMUNITY"

    elif "NEWS" in page_text_upper:
        article_type = "NEWS"

    return {
        "title": title or "Unknown",
        "date": date or "Unknown",
        "type": article_type or "UNKNOWN"
    }


def extract_sections(soup):
    sections = []

    blocks = soup.select(
        ".news-section-block"
    )

    print(
        f"Secciones encontradas: {len(blocks)}"
    )

    for index, block in enumerate(blocks, start=1):

        # ----------------------------------------------------
        # HEADER
        # ----------------------------------------------------

        title_element = block.select_one(
            ".section-header .title"
        )

        author_element = block.select_one(
            ".section-header .author"
        )

        title = clean_text(
            title_element.get_text(
                " ",
                strip=True
            )
            if title_element
            else ""
        )

        author = clean_text(
            author_element.get_text(
                " ",
                strip=True
            )
            if author_element
            else ""
        )

        # ----------------------------------------------------
        # CONTENT
        # ----------------------------------------------------

        content_element = block.select_one(
            ".content"
        )

        content = ""

        if content_element:
            content = clean_text(
                content_element.get_text(
                    " ",
                    strip=True
                )
            )

        # ----------------------------------------------------
        # IMAGES
        # ----------------------------------------------------

        images = []

        if content_element:
            for image in content_element.select("img"):

                src = image.get("src")

                if not src:
                    continue

                image_url = urljoin(
                    BASE_URL,
                    src
                )

                if image_url not in images:
                    images.append(
                        image_url
                    )

        # ----------------------------------------------------
        # SKIP EMPTY / PLACEHOLDER TITLES
        # ----------------------------------------------------

        if not title:
            continue

        if title == "⠀":
            continue

        if not content:
            continue

        sections.append({
            "section_index": index,
            "title": title,
            "author": author,
            "content": content,
            "images": images
        })

    return sections


def scrape_latest_article():
    url = get_latest_news()

    print(f"Último artículo: {url}")

    response = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; CalaveraGamingTV Rust News Bot)"
            )
        }
    )

    response.raise_for_status()

    html = response.text

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    metadata = extract_article_metadata(
        soup,
        html
    )

    sections = extract_sections(
        soup
    )

    print(
        f"Título detectado: {metadata['title']}"
    )

    print(
        f"Fecha detectada: {metadata['date']}"
    )

    print(
        f"Tipo detectado: {metadata['type']}"
    )

    return {
        "url": url,
        "title": metadata["title"],
        "date": metadata["date"],
        "type": metadata["type"],
        "sections": sections
    }


# ============================================================
# GEMINI - SECTION ANALYSIS
# ============================================================

def build_sections_for_prompt(sections):
    blocks = []

    for index, section in enumerate(
        sections,
        start=1
    ):
        block = (
            f"SECCIÓN {index}\n"
            f"TÍTULO: {section['title']}\n"
            f"AUTOR: {section['author']}\n"
            f"CONTENIDO:\n"
            f"{section['content']}\n"
        )

        blocks.append(block)

    return "\n\n".join(blocks)


def analyze_sections(article):
    prompt_template = load_prompt(
        ANALYZE_PROMPT_FILE
    )

    sections_text = build_sections_for_prompt(
        article["sections"]
    )

    prompt = (
        prompt_template
        .replace(
            "{{ARTICLE_TITLE}}",
            article["title"]
        )
        .replace(
            "{{ARTICLE_DATE}}",
            article["date"]
        )
        .replace(
            "{{ARTICLE_TYPE}}",
            article["type"]
        )
        .replace(
            "{{SECTIONS}}",
            sections_text
        )
    )

    print(
        "Analizando secciones con Gemini..."
    )

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )

    result = parse_json_response(
        response.text
    )

    if not isinstance(result, list):
        raise ValueError(
            "El análisis de Gemini no devolvió un array."
        )

    analyzed_sections = []

    for original_section, analysis in zip(
        article["sections"],
        result
    ):
        item = {
            **original_section,
            **analysis
        }

        analyzed_sections.append(
            item
        )

    return analyzed_sections


# ============================================================
# CONTENT QUEUE
# ============================================================

def create_queue(
    article,
    analyzed_sections
):
    selected = []

    for section in analyzed_sections:

        publication_type = section.get(
            "publication_type",
            "skip"
        )

        score = section.get(
            "publication_score",
            0
        )

        try:
            score = int(score)
        except (TypeError, ValueError):
            score = 0

        if publication_type == "skip":
            continue

        if publication_type == "related":
            continue

        if score < MINIMUM_PUBLICATION_SCORE:
            continue

        selected.append(
            section
        )

    # Ordenamos por publication score.
    selected.sort(
        key=lambda item: int(
            item.get(
                "publication_score",
                0
            )
        ),
        reverse=True
    )

    items = []

    for priority, section in enumerate(
        selected,
        start=1
    ):
        items.append({
            "article_url": article["url"],
            "article_title": article["title"],
            "article_date": article["date"],
            "article_type": article["type"],

            "title": section.get(
                "title"
            ),

            "author": section.get(
                "author",
                ""
            ),

            "content": section.get(
                "content",
                ""
            ),

            "images": section.get(
                "images",
                []
            ),

            "importance": section.get(
                "importance",
                0
            ),

            "interaction_potential": section.get(
                "interaction_potential",
                0
            ),

            "social_value": section.get(
                "social_value",
                0
            ),

            "publication_score": section.get(
                "publication_score",
                0
            ),

            "recommended": section.get(
                "recommended",
                False
            ),

            "publication_type": section.get(
                "publication_type",
                "standalone"
            ),

            "content_type": section.get(
                "content_type",
                "news"
            ),

            "reason": section.get(
                "reason",
                ""
            ),

            "published": False,
            "published_at": None,
            "platform": None,
            "post_id": None,

            "generated_text": None,
            "generated_at": None,

            "priority": priority
        })

    queue = {
        "article": {
            "url": article["url"],
            "title": article["title"],
            "date": article["date"],
            "type": article["type"]
        },

        "general_publication": {
            "discord_posted": False,
            "discord_posted_at": None,

            "x_posted": False,
            "x_posted_at": None,
            "x_post_id": None
        },

        "selection": {
            "minimum_publication_score": (
                MINIMUM_PUBLICATION_SCORE
            ),
            "total_sections": len(
                article["sections"]
            ),
            "selected_sections": len(
                items
            )
        },

        "items": items
    }

    return queue


def is_same_article(queue, article):
    if not queue:
        return False

    queue_article = queue.get(
        "article",
        {}
    )

    return (
        queue_article.get("url")
        == article["url"]
    )


# ============================================================
# LAST POSTS
# ============================================================

def get_last_posts(queue, limit=5):
    """
    Recupera los últimos posts generados/publicados
    para que Gemini pueda evitar repetir estructuras.

    Por ahora usamos la cola actual y los items que
    ya tengan generated_text.
    """

    posts = []

    if not queue:
        return posts

    items = queue.get(
        "items",
        []
    )

    published_items = [
        item
        for item in items
        if item.get("generated_text")
    ]

    published_items.sort(
        key=lambda item: item.get(
            "generated_at"
        ) or "",
        reverse=True
    )

    for item in published_items[:limit]:
        posts.append(
            item.get(
                "generated_text"
            )
        )

    return posts


def format_last_posts(last_posts):
    if not last_posts:
        return "No hay posts anteriores disponibles."

    result = []

    for index, post in enumerate(
        last_posts,
        start=1
    ):
        result.append(
            f"POST {index}:\n{post}"
        )

    return "\n\n".join(result)


# ============================================================
# GENERAL PATCH ANNOUNCEMENT
# ============================================================

def generate_general_announcement(
    article,
    queue
):
    """
    Genera X + Discord en una sola llamada.

    IMPORTANTE:
    Esta función NO publica nada.
    """

    prompt_template = load_prompt(
        GENERAL_ANNOUNCEMENT_PROMPT_FILE
    )

    last_posts = get_last_posts(
        queue
    )

    last_posts_text = format_last_posts(
        last_posts
    )

    sections_for_prompt = []

    for item in queue.get(
        "items",
        []
    ):
        sections_for_prompt.append(
            (
                f"TÍTULO: {item.get('title', '')}\n"
                f"IMPORTANCIA: {item.get('importance', 0)}\n"
                f"INTERACCIÓN: {item.get('interaction_potential', 0)}\n"
                f"VALOR SOCIAL: {item.get('social_value', 0)}\n"
                f"PUBLICATION SCORE: {item.get('publication_score', 0)}\n"
                f"TIPO DE CONTENIDO: {item.get('content_type', '')}\n"
                f"RAZÓN: {item.get('reason', '')}\n"
                f"CONTENIDO:\n{item.get('content', '')}"
            )
        )

    sections_text = "\n\n".join(
        sections_for_prompt
    )

    prompt = (
        prompt_template
        .replace(
            "{{ARTICLE_TITLE}}",
            article["title"]
        )
        .replace(
            "{{ARTICLE_DATE}}",
            article["date"]
        )
        .replace(
            "{{ARTICLE_TYPE}}",
            article["type"]
        )
        .replace(
            "{{LAST_POSTS}}",
            last_posts_text
        )
        .replace(
            "{{SECTIONS}}",
            sections_text
        )
    )

    print(
        "\nGenerando anuncio general del patch..."
    )

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )

    result = parse_json_response(
        response.text
    )

    if not isinstance(result, dict):
        raise ValueError(
            "El anuncio general no devolvió un objeto JSON."
        )

    x_text = result.get(
        "x_text"
    )

    discord_text = result.get(
        "discord_text"
    )

    if not x_text:
        raise ValueError(
            "Gemini no devolvió x_text."
        )

    if not discord_text:
        raise ValueError(
            "Gemini no devolvió discord_text."
        )

    return {
        "x_text": x_text.strip(),
        "discord_text": discord_text.strip()
    }


# ============================================================
# X POST GENERATION
# ============================================================

def generate_x_post(item):
    prompt_template = load_prompt(
        X_POST_PROMPT_FILE
    )

    prompt = (
        prompt_template
        .replace(
            "{{SECTION_TITLE}}",
            item.get(
                "title",
                ""
            )
        )
        .replace(
            "{{SECTION_CONTENT}}",
            item.get(
                "content",
                ""
            )
        )
        .replace(
            "{{ARTICLE_TITLE}}",
            item.get(
                "article_title",
                ""
            )
        )
        .replace(
            "{{ARTICLE_DATE}}",
            item.get(
                "article_date",
                ""
            )
        )
    )

    print(
        f"Generando post X para: "
        f"{item.get('title')}"
    )

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )

    text = response.text.strip()

    if not text:
        raise ValueError(
            "Gemini devolvió un post vacío."
        )

    # Por seguridad, eliminamos bloques de código
    # si Gemini los agrega.
    text = re.sub(
        r"^```(?:text)?\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\s*```$",
        "",
        text
    )

    text = text.strip()

    return text


# ============================================================
# BUFFER
# ============================================================

def send_to_buffer(
    message,
    images=None
):
    if not BUFFER_API_KEY:
        raise RuntimeError(
            "BUFFER_API_KEY no está configurada."
        )

    if not BUFFER_CHANNEL_ID:
        raise RuntimeError(
            "BUFFER_CHANNEL_ID no está configurada."
        )

    query = """
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on Post {
          id
          text
          assets {
            id
            mimeType
          }
        }
        ... on CreatePostError {
          message
        }
      }
    }
    """

    input_data = {
        "text": message,
        "channelId": BUFFER_CHANNEL_ID,
        "schedulingType": "automatic",
        "mode": "shareNow"
    }

    valid_images = []

    if images:
        for image_url in images:

            if not image_url:
                continue

            if (
                not image_url.startswith(
                    "http://"
                )
                and
                not image_url.startswith(
                    "https://"
                )
            ):
                continue

            valid_images.append(
                image_url
            )

    if valid_images:
        input_data["assets"] = [
            {
                "image": {
                    "url": valid_images[0]
                }
            }
        ]

    headers = {
        "Authorization": (
            f"Bearer {BUFFER_API_KEY}"
        ),
        "Content-Type": "application/json"
    }

    response = requests.post(
        "https://api.buffer.com",
        headers=headers,
        json={
            "query": query,
            "variables": {
                "input": input_data
            }
        },
        timeout=30
    )

    response.raise_for_status()

    result = response.json()

    if result.get("errors"):
        raise RuntimeError(
            "Buffer API error: "
            + json.dumps(
                result["errors"],
                ensure_ascii=False
            )
        )

    create_post = result.get(
        "data",
        {}
    ).get(
        "createPost"
    )

    if not create_post:
        raise RuntimeError(
            "Buffer no devolvió createPost."
        )

    if create_post.get("message") and not create_post.get("id"):
        raise RuntimeError(
            f"Buffer rechazó el post: "
            f"{create_post.get('message')}"
        )

    if not create_post.get("id"):
        raise RuntimeError(
            "Buffer no devolvió un post ID."
        )

    return create_post


# ============================================================
# DAILY CONTENT PUBLICATION
# ============================================================

def get_next_unpublished_item(queue):
    items = queue.get(
        "items",
        []
    )

    unpublished = [
        item
        for item in items
        if not item.get("published", False)
    ]

    if not unpublished:
        return None

    unpublished.sort(
        key=lambda item: item.get(
            "priority",
            999999
        )
    )

    return unpublished[0]


def publish_next_content(queue):
    item = get_next_unpublished_item(
        queue
    )

    if not item:
        print(
            "No quedan secciones pendientes para publicar."
        )
        return False

    print(
        "\n----------------------------------------"
    )

    print(
        "Próximo contenido:"
    )

    print(
        f"Título: {item.get('title')}"
    )

    print(
        f"Score: {item.get('publication_score')}"
    )

    print(
        f"Prioridad: {item.get('priority')}"
    )

    # --------------------------------------------------------
    # GENERATE
    # --------------------------------------------------------

    generated_text = generate_x_post(
        item
    )

    print(
        "\nPost generado:"
    )

    print(
        generated_text
    )

    # --------------------------------------------------------
    # IMAGE
    # --------------------------------------------------------

    images = item.get(
        "images",
        []
    )

    if images:
        print(
            f"Imagen encontrada: {images[0]}"
        )
    else:
        print(
            "No hay imagen para este contenido."
        )

    # --------------------------------------------------------
    # BUFFER
    # --------------------------------------------------------

    print(
        "\nPublicando mediante Buffer..."
    )

    post = send_to_buffer(
        generated_text,
        images=images
    )

    post_id = post.get(
        "id"
    )

    print(
        f"Publicado correctamente en Buffer. ID: {post_id}"
    )

    # --------------------------------------------------------
    # SAVE STATE ONLY AFTER SUCCESS
    # --------------------------------------------------------

    now = datetime.now(
        timezone.utc
    ).isoformat()

    item["generated_text"] = generated_text
    item["generated_at"] = now

    item["published"] = True
    item["published_at"] = now

    item["platform"] = "x"
    item["post_id"] = post_id

    save_json(
        QUEUE_FILE,
        queue
    )

    print(
        "Estado guardado correctamente."
    )

    print(
        "----------------------------------------"
    )

    return True


# ============================================================
# DEBUG / GENERAL ANNOUNCEMENT PREVIEW
# ============================================================

def preview_general_announcement(
    article,
    queue
):
    """
    Genera el anuncio general pero NO publica.

    Esto nos permite validar el prompt antes de
    conectar Discord + Buffer para este flujo.
    """

    publication = queue.get(
        "general_publication"
    )

    if not publication:
        publication = {
            "discord_posted": False,
            "discord_posted_at": None,
            "x_posted": False,
            "x_posted_at": None,
            "x_post_id": None
        }

        queue["general_publication"] = publication

    # --------------------------------------------------------
    # NO REGENERATE IF ALREADY PUBLISHED
    # --------------------------------------------------------

    if (
        publication.get("x_posted")
        or publication.get("discord_posted")
    ):
        print(
            "\nEl anuncio general ya tiene actividad registrada."
        )

        return None

    announcement = generate_general_announcement(
        article,
        queue
    )

    print(
        "\n========================================"
    )

    print(
        "ANUNCIO GENERAL - X"
    )

    print(
        "========================================"
    )

    print(
        announcement["x_text"]
    )

    print(
        "\n========================================"
    )

    print(
        "ANUNCIO GENERAL - DISCORD"
    )

    print(
        "========================================"
    )

    print(
        announcement["discord_text"]
    )

    print(
        "\n========================================"
    )

    return announcement


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "========================================"
    )

    print(
        "CALAVERA GAMING TV - RUST NEWS"
    )

    print(
        "========================================"
    )

    # --------------------------------------------------------
    # 1. SCRAPE LATEST ARTICLE
    # --------------------------------------------------------

    article = scrape_latest_article()

    # --------------------------------------------------------
    # 2. SAVE LATEST NEWS
    # --------------------------------------------------------

    save_json(
        LATEST_NEWS_FILE,
        {
            "url": article["url"],
            "title": article["title"],
            "date": article["date"],
            "type": article["type"]
        }
    )

    # --------------------------------------------------------
    # 3. LOAD EXISTING QUEUE
    # --------------------------------------------------------

    existing_queue = load_json(
        QUEUE_FILE,
        None
    )

    # --------------------------------------------------------
    # 4. NEW ARTICLE?
    # --------------------------------------------------------

    if not is_same_article(
        existing_queue,
        article
    ):
        print(
            "\nDetectado nuevo artículo."
        )

        # ----------------------------------------------------
        # ANALYZE
        # ----------------------------------------------------

        analyzed_sections = analyze_sections(
            article
        )

        save_json(
            NEWS_ANALYSIS_FILE,
            {
                "article": {
                    "url": article["url"],
                    "title": article["title"],
                    "date": article["date"],
                    "type": article["type"]
                },
                "sections": analyzed_sections
            }
        )

        # ----------------------------------------------------
        # CREATE QUEUE
        # ----------------------------------------------------

        queue = create_queue(
            article,
            analyzed_sections
        )

        save_json(
            QUEUE_FILE,
            queue
        )

        print(
            "\nNueva cola creada."
        )

        print(
            f"Secciones totales: "
            f"{queue['selection']['total_sections']}"
        )

        print(
            f"Secciones seleccionadas: "
            f"{queue['selection']['selected_sections']}"
        )

    else:
        queue = existing_queue

        print(
            "\nNo hay un nuevo artículo."
        )

    # --------------------------------------------------------
    # 5. GENERAL ANNOUNCEMENT
    # --------------------------------------------------------

    general_publication = queue.get(
        "general_publication",
        {}
    )

    if not (
        general_publication.get(
            "x_posted",
            False
        )
        or
        general_publication.get(
            "discord_posted",
            False
        )
    ):
        print(
            "\nGenerando preview del anuncio general..."
        )

        preview_general_announcement(
            article,
            queue
        )

    else:
        print(
            "\nAnuncio general ya procesado."
        )

    # --------------------------------------------------------
    # 6. DAILY SECTION CONTENT
    # --------------------------------------------------------

    publish_next_content(
        queue
    )

    # --------------------------------------------------------
    # FINAL SAVE
    # --------------------------------------------------------

    save_json(
        QUEUE_FILE,
        queue
    )

    print(
        "\n========================================"
    )

    print(
        "FIN"
    )

    print(
        "========================================"
    )


if __name__ == "__main__":
    main()
