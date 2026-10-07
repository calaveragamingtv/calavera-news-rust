import os
import json
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from google import genai


BASE_URL = "https://rust.facepunch.com"
NEWS_URL = "https://rust.facepunch.com/news/"

DATA_DIR = "data"
PROMPT_DIR = "prompt"

LATEST_NEWS_FILE = os.path.join(DATA_DIR, "latest_news.json")
NEWS_ANALYSIS_FILE = os.path.join(DATA_DIR, "news_analysis.json")
QUEUE_FILE = os.path.join(DATA_DIR, "content_queue.json")

ANALYZE_PROMPT_FILE = os.path.join(
    PROMPT_DIR,
    "analyze_devblog_sections.txt"
)

X_PROMPT_FILE = os.path.join(
    PROMPT_DIR,
    "generate_x_post.txt"
)

GEMINI_MODEL = "gemini-3.5-flash-lite"

MINIMUM_PUBLICATION_SCORE = 75


# ============================================================
# UTILIDADES
# ============================================================

def load_json(path, default=None):
    if not os.path.exists(path):
        return default

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


def load_prompt(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def clean_json_response(text):
    text = text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    return text.strip()


def get_gemini_client():
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "No existe GEMINI_API_KEY en las variables de entorno."
        )

    return genai.Client(api_key=api_key)


# ============================================================
# SCRAPER
# ============================================================

def get_latest_news():
    print("Buscando último artículo de Rust...")

    response = requests.get(
        NEWS_URL,
        timeout=30,
        headers={
            "User-Agent": "CalaveraRustNews/1.0"
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

        return urljoin(BASE_URL, href)

    raise RuntimeError(
        "No se pudo detectar el último artículo de Rust."
    )


def extract_article_metadata(soup):
    html_title = ""

    if soup.title:
        html_title = soup.title.get_text(
            " ",
            strip=True
        )

    h1 = soup.find("h1")

    title = ""

    if h1:
        title = h1.get_text(
            " ",
            strip=True
        )

    if not title:
        title = html_title

    if title.endswith(" - News - Rust"):
        title = title.replace(
            " - News - Rust",
            ""
        ).strip()

    page_text = soup.get_text(
        " ",
        strip=True
    )

    date = ""

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

    article_type = ""

    if soup.select('a[href*="/news/"]'):
        article_type = "DEVBLOG"

    print()
    print("DEBUG metadata:")
    print(
        "HTML title:",
        html_title if html_title else "NO ENCONTRADO"
    )
    print(
        "h1:",
        h1.get_text(" ", strip=True)
        if h1
        else "NO ENCONTRADO"
    )
    print(
        "time:",
        "ENCONTRADO" if soup.find("time") else "NO ENCONTRADO"
    )
    print(
        "DEVBLOG links:",
        len(soup.select('a[href*="/news/"]'))
    )

    return {
        "title": title,
        "date": date,
        "type": article_type
    }


def parse_sections(soup):
    sections = []

    blocks = soup.select(
        ".news-section-block"
    )

    print(
        "Secciones encontradas:",
        len(blocks)
    )

    for block in blocks:
        header = block.select_one(
            ".section-header"
        )

        if not header:
            continue

        title_element = header.select_one(
            ".title"
        )

        author_element = header.select_one(
            ".author"
        )

        title = (
            title_element.get_text(
                " ",
                strip=True
            )
            if title_element
            else ""
        )

        author = (
            author_element.get_text(
                " ",
                strip=True
            )
            if author_element
            else ""
        )

        if not title or title == "⠀":
            continue

        content_element = block.select_one(
            ".content"
        )

        if not content_element:
            continue

        content = content_element.get_text(
            "\n",
            strip=True
        )

        images = []

        for image in content_element.select("img"):
            src = image.get("src")

            if not src:
                continue

            image_url = urljoin(
                BASE_URL,
                src
            )

            images.append(image_url)

        sections.append(
            {
                "title": title,
                "author": author,
                "content": content,
                "images": images
            }
        )

    return sections


def scrape_article(url):
    print()
    print("Descargando artículo:")
    print(url)

    response = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "CalaveraRustNews/1.0"
        }
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    metadata = extract_article_metadata(
        soup
    )

    sections = parse_sections(
        soup
    )

    print(
        "Título detectado:",
        metadata["title"]
    )

    print(
        "Fecha detectada:",
        metadata["date"]
    )

    print(
        "Tipo detectado:",
        metadata["type"]
    )

    return {
        "url": url,
        "title": metadata["title"],
        "date": metadata["date"],
        "type": metadata["type"],
        "sections": sections
    }


# ============================================================
# GEMINI - ANALISIS
# ============================================================

def analyze_article(article):
    print()
    print("ANALIZANDO ARTÍCULO COMPLETO CON GEMINI...")

    prompt_template = load_prompt(
        ANALYZE_PROMPT_FILE
    )

    sections_text = []

    for index, section in enumerate(
        article["sections"],
        start=1
    ):
        sections_text.append(
            f"""
SECCIÓN {index}

Título: {section["title"]}
Autor: {section["author"]}

Contenido:
{section["content"]}
""".strip()
        )

    prompt = prompt_template

    prompt = prompt.replace(
        "{{ARTICLE_TITLE}}",
        article["title"]
    )

    prompt = prompt.replace(
        "{{ARTICLE_DATE}}",
        article["date"]
    )

    prompt = prompt.replace(
        "{{ARTICLE_TYPE}}",
        article["type"]
    )

    prompt = prompt.replace(
        "{{SECTIONS}}",
        "\n\n".join(sections_text)
    )

    client = get_gemini_client()

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )

    raw_text = response.text

    clean_text = clean_json_response(
        raw_text
    )

    try:
        analysis = json.loads(
            clean_text
        )
    except json.JSONDecodeError as e:
        print()
        print("ERROR: Gemini no devolvió JSON válido.")
        print(raw_text)
        raise e

    if not isinstance(analysis, list):
        raise RuntimeError(
            "La respuesta de Gemini no es una lista."
        )

    return analysis


# ============================================================
# COLA DE CONTENIDOS
# ============================================================

def build_queue(article, analysis):
    selected = []

    analysis_by_title = {}

    for result in analysis:
        title = result.get("title")

        if title:
            analysis_by_title[title] = result

    for section in article["sections"]:
        result = analysis_by_title.get(
            section["title"]
        )

        if not result:
            continue

        publication_type = result.get(
            "publication_type",
            "skip"
        )

        publication_score = result.get(
            "publication_score",
            0
        )

        if publication_type != "standalone":
            continue

        if publication_score < MINIMUM_PUBLICATION_SCORE:
            continue

        selected.append(
            {
                "article_url": article["url"],
                "article_title": article["title"],
                "article_date": article["date"],
                "article_type": article["type"],

                "title": section["title"],
                "author": section["author"],
                "content": section["content"],
                "images": section.get(
                    "images",
                    []
                ),

                "importance": result.get(
                    "importance",
                    0
                ),

                "interaction_potential": result.get(
                    "interaction_potential",
                    0
                ),

                "social_value": result.get(
                    "social_value",
                    0
                ),

                "publication_score": publication_score,

                "recommended": result.get(
                    "recommended",
                    True
                ),

                "publication_type": publication_type,

                "content_type": result.get(
                    "content_type",
                    "news"
                ),

                "reason": result.get(
                    "reason",
                    ""
                ),

                "published": False,
                "published_at": None,
                "platform": None,
                "post_id": None,

                "generated_text": None,
                "generated_at": None,

                "priority": 0
            }
        )

    selected.sort(
        key=lambda item: (
            item["publication_score"],
            item["interaction_potential"],
            item["importance"],
            item["social_value"]
        ),
        reverse=True
    )

    for index, item in enumerate(
        selected,
        start=1
    ):
        item["priority"] = index

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
            "minimum_publication_score":
                MINIMUM_PUBLICATION_SCORE,

            "total_sections":
                len(article["sections"]),

            "selected_sections":
                len(selected)
        },

        "items": selected
    }

    return queue


def create_or_update_queue(article):
    existing_queue = load_json(
        QUEUE_FILE,
        None
    )

    if existing_queue:
        existing_article = existing_queue.get(
            "article",
            {}
        )

        if existing_article.get("url") == article["url"]:
            print()
            print("♻️ PATCH ACTUAL YA ESTÁ EN COLA")

            return existing_queue

    print()
    print("🆕 NUEVO PATCH DETECTADO")

    analysis = analyze_article(
        article
    )

    save_json(
        NEWS_ANALYSIS_FILE,
        analysis
    )

    queue = build_queue(
        article,
        analysis
    )

    save_json(
        QUEUE_FILE,
        queue
    )

    return queue


# ============================================================
# X POST
# ============================================================

def get_last_published_posts(queue, limit=5):
    posts = []

    for item in queue.get(
        "items",
        []
    ):
        if not item.get("published"):
            continue

        generated_text = item.get(
            "generated_text"
        )

        if not generated_text:
            continue

        posts.append(
            {
                "text": generated_text,
                "published_at": item.get(
                    "published_at"
                )
            }
        )

    posts.sort(
        key=lambda post: (
            post.get("published_at")
            or ""
        ),
        reverse=True
    )

    return posts[:limit]


def generate_x_post(item, queue):
    print()
    print("GENERANDO POST PARA X...")

    prompt_template = load_prompt(
        X_PROMPT_FILE
    )

    last_posts = get_last_published_posts(
        queue
    )

    if last_posts:
        last_posts_text = "\n".join(
            f"- {post['text']}"
            for post in last_posts
        )
    else:
        last_posts_text = (
            "No hay posts anteriores."
        )

    prompt = prompt_template

    prompt = prompt.replace(
        "{{ARTICLE_TITLE}}",
        item["article_title"]
    )

    prompt = prompt.replace(
        "{{ARTICLE_DATE}}",
        item["article_date"]
    )

    prompt = prompt.replace(
        "{{SECTION_TITLE}}",
        item["title"]
    )

    prompt = prompt.replace(
        "{{AUTHOR}}",
        item["author"]
    )

    prompt = prompt.replace(
        "{{CONTENT_TYPE}}",
        item["content_type"]
    )

    prompt = prompt.replace(
        "{{REASON}}",
        item["reason"]
    )

    prompt = prompt.replace(
        "{{IMPORTANCE}}",
        str(item["importance"])
    )

    prompt = prompt.replace(
        "{{INTERACTION_POTENTIAL}}",
        str(item["interaction_potential"])
    )

    prompt = prompt.replace(
        "{{SOCIAL_VALUE}}",
        str(item["social_value"])
    )

    prompt = prompt.replace(
        "{{LAST_POSTS}}",
        last_posts_text
    )

    prompt = prompt.replace(
        "{{CONTENT}}",
        item["content"]
    )

    client = get_gemini_client()

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )

    raw_text = response.text

    clean_text = clean_json_response(
        raw_text
    )

    try:
        result = json.loads(
            clean_text
        )
    except json.JSONDecodeError as e:
        print()
        print("ERROR: Gemini no devolvió JSON válido.")
        print(raw_text)
        raise e

    generated_text = result.get(
        "text"
    )

    if not generated_text:
        raise RuntimeError(
            "Gemini no devolvió el campo 'text'."
        )

    generated_text = generated_text.strip()

    print()
    print("POST GENERADO")
    print("----------------------------------------")
    print(generated_text)
    print("----------------------------------------")

    return generated_text


# ============================================================
# BUFFER
# ============================================================

def send_to_buffer(message, images=None):
    buffer_api_key = os.getenv(
        "BUFFER_API_KEY"
    )

    buffer_channel_id = os.getenv(
        "BUFFER_CHANNEL_ID"
    )

    if not buffer_api_key:
        raise RuntimeError(
            "No existe BUFFER_API_KEY."
        )

    if not buffer_channel_id:
        raise RuntimeError(
            "No existe BUFFER_CHANNEL_ID."
        )

    query = """
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess {
          post {
            id
            text
            assets {
              id
              mimeType
            }
          }
        }
        ... on MutationError {
          message
        }
      }
    }
    """

    input_data = {
        "text": message,
        "channelId": buffer_channel_id,
        "schedulingType": "automatic",
        "mode": "shareNow"
    }

    # --------------------------------------------------------
    # IMAGEN
    # --------------------------------------------------------

    valid_images = []

    if images:
        for image_url in images:
            if not image_url:
                continue

            if not image_url.startswith(
                "http://"
            ) and not image_url.startswith(
                "https://"
            ):
                continue

            valid_images.append(
                image_url
            )

    # Por ahora usamos solamente la primera imagen.
    # Evitamos convertir un post simple en un carrusel
    # sin necesidad.
    if valid_images:
        input_data["assets"] = [
            {
                "image": {
                    "url": valid_images[0]
                }
            }
        ]

    payload = {
        "query": query,
        "variables": {
            "input": input_data
        }
    }

    print()
    print("ENVIANDO A BUFFER...")

    if valid_images:
        print(
            "Imagen adjunta:",
            valid_images[0]
        )
    else:
        print(
            "Imagen adjunta: ninguna"
        )

    response = requests.post(
        "https://api.buffer.com",
        headers={
            "Authorization": (
                f"Bearer {buffer_api_key}"
            ),
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=30
    )

    response.raise_for_status()

    result = response.json()

    if result.get("errors"):
        raise RuntimeError(
            f"Buffer API error: {result['errors']}"
        )

    create_post = result.get(
        "data",
        {}
    ).get(
        "createPost"
    )

    if not create_post:
        raise RuntimeError(
            f"Respuesta inesperada de Buffer: {result}"
        )

    if create_post.get("message"):
        raise RuntimeError(
            f"Buffer error: {create_post['message']}"
        )

    post = create_post.get(
        "post"
    )

    if not post:
        raise RuntimeError(
            f"Buffer no devolvió el post: {result}"
        )

    print(
        "✅ Message sent to X via Buffer."
    )

    print(
        "Buffer post ID:",
        post.get("id")
    )

    assets = post.get(
        "assets"
    ) or []

    if assets:
        print(
            "✅ Imagen adjunta correctamente."
        )
        print(
            "Assets:",
            len(assets)
        )
    else:
        print(
            "ℹ️ Buffer no devolvió assets."
        )

    return post


# ============================================================
# PUBLICAR SIGUIENTE CONTENIDO
# ============================================================

def publish_next_content(queue):
    print()
    print("PATCH:")
    print(
        queue["article"]["title"]
    )

    general = queue.get(
        "general_publication",
        {}
    )

    print(
        "Discord general publicado:",
        general.get(
            "discord_posted",
            False
        )
    )

    print(
        "X general publicado:",
        general.get(
            "x_posted",
            False
        )
    )

    pending_items = [
        item
        for item in queue.get(
            "items",
            []
        )
        if not item.get("published")
    ]

    if not pending_items:
        print()
        print(
            "✅ NO HAY CONTENIDO PENDIENTE"
        )
        return

    pending_items.sort(
        key=lambda item: item.get(
            "priority",
            999
        )
    )

    item = pending_items[0]

    print()
    print(
        "SIGUIENTE CONTENIDO PENDIENTE"
    )

    print(
        "Priority:",
        item.get("priority")
    )

    print(
        "Título:",
        item.get("title")
    )

    print(
        "Score:",
        item.get(
            "publication_score"
        )
    )

    print(
        "Tipo:",
        item.get(
            "content_type"
        )
    )

    images = item.get(
        "images",
        []
    )

    if images:
        print(
            "Imágenes disponibles:",
            len(images)
        )

        print(
            "Primera imagen:",
            images[0]
        )
    else:
        print(
            "Imágenes disponibles: 0"
        )

    generated_text = generate_x_post(
        item,
        queue
    )

    post = send_to_buffer(
        generated_text,
        images=images
    )

    # --------------------------------------------------------
    # IMPORTANTE:
    # Solamente marcamos como publicado después
    # de que Buffer confirmó correctamente.
    # --------------------------------------------------------

    now = datetime.now(
        timezone.utc
    ).isoformat()

    item["generated_text"] = (
        generated_text
    )

    item["generated_at"] = now

    item["published"] = True

    item["published_at"] = now

    item["platform"] = "x"

    item["post_id"] = post.get(
        "id"
    )

    save_json(
        QUEUE_FILE,
        queue
    )

    print()
    print(
        "========================================"
    )
    print(
        "✅ CONTENIDO PUBLICADO"
    )
    print(
        "========================================"
    )

    print(
        "Post ID:",
        post.get("id")
    )

    print(
        "Publicado:",
        now
    )


# ============================================================
# MAIN
# ============================================================

def main():
    print()
    print(
        "========================================"
    )
    print(
        "CALAVERA RUST NEWS"
    )
    print(
        "========================================"
    )

    latest_url = get_latest_news()

    print()
    print(
        "Último artículo detectado:"
    )
    print(
        latest_url
    )

    article = scrape_article(
        latest_url
    )

    save_json(
        LATEST_NEWS_FILE,
        {
            "url": article["url"],
            "title": article["title"],
            "date": article["date"],
            "type": article["type"]
        }
    )

    queue = create_or_update_queue(
        article
    )

    publish_next_content(
        queue
    )


if __name__ == "__main__":
    main()
