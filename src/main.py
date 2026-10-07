import os
import json
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from google import genai


# ============================================================
# CONFIG
# ============================================================

BASE_URL = "https://rust.facepunch.com"
NEWS_URL = f"{BASE_URL}/news/"

LATEST_NEWS_FILE = "data/latest_news.json"
NEWS_ANALYSIS_FILE = "data/news_analysis.json"
QUEUE_FILE = "data/content_queue.json"

ANALYZE_PROMPT_FILE = "prompt/analyze_devblog_sections.txt"
X_POST_PROMPT_FILE = "prompt/generate_x_post.txt"

GEMINI_MODEL = "gemini-3.5-flash-lite"


# ============================================================
# JSON HELPERS
# ============================================================

def load_json(path, default=None):
    if not os.path.exists(path):
        return default

    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    directory = os.path.dirname(path)

    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )


# ============================================================
# PROMPT HELPERS
# ============================================================

def load_prompt(path):
    with open(path, "r", encoding="utf-8") as file:
        return file.read()


# ============================================================
# SCRAPER
# ============================================================

def get_latest_news():
    print("Buscando último artículo de Rust...")

    response = requests.get(
        NEWS_URL,
        timeout=30
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
        "No se pudo detectar el último artículo de Rust."
    )


def parse_article(url):
    print("Descargando artículo:")
    print(url)

    response = requests.get(
        url,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    # --------------------------------------------------------
    # DEBUG METADATA
    # --------------------------------------------------------

    html_title = (
        soup.title.get_text(
            strip=True
        )
        if soup.title
        else "NO ENCONTRADO"
    )

    h1 = soup.find("h1")

    h1_text = (
        h1.get_text(
            strip=True
        )
        if h1
        else "NO ENCONTRADO"
    )

    time_tag = soup.find("time")

    time_text = (
        time_tag.get_text(
            strip=True
        )
        if time_tag
        else "NO ENCONTRADO"
    )

    devblog_links = soup.find_all(
        string=re.compile(
            "DEVBLOG",
            re.IGNORECASE
        )
    )

    sections = soup.select(
        ".news-section-block"
    )

    print("DEBUG metadata:")
    print(f"HTML title: {html_title}")
    print(f"h1: {h1_text}")
    print(f"time: {time_text}")
    print(f"DEVBLOG links: {len(devblog_links)}")
    print(f"Secciones encontradas: {len(sections)}")

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    title = html_title

    if title.endswith(" - News - Rust"):
        title = title.replace(
            " - News - Rust",
            ""
        ).strip()

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    article_date = None

    full_text = soup.get_text(
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
            full_text
        )

        if match:
            article_date = match.group(0)
            break

    if not article_date:
        for pattern in date_patterns:
            match = re.search(
                pattern,
                response.text
            )

            if match:
                article_date = match.group(0)
                break

    # --------------------------------------------------------
    # TYPE
    # --------------------------------------------------------

    article_type = "DEVBLOG"

    # --------------------------------------------------------
    # SECTIONS
    # --------------------------------------------------------

    parsed_sections = []

    for section in sections:

        header = section.select_one(
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

        content_element = section.select_one(
            ".content"
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
            for image in content_element.select("img"):
                src = image.get("src")

                if not src:
                    continue

                images.append(
                    urljoin(
                        BASE_URL,
                        src
                    )
                )

        parsed_sections.append(
            {
                "title": section_title,
                "author": author,
                "content": content,
                "images": images
            }
        )

    print(f"Título detectado: {title}")
    print(
        f"Fecha detectada: "
        f"{article_date or 'NO ENCONTRADA'}"
    )
    print(f"Tipo detectado: {article_type}")

    return {
        "url": url,
        "title": title,
        "date": article_date,
        "type": article_type,
        "sections": parsed_sections
    }


# ============================================================
# GEMINI
# ============================================================

def get_gemini_client():
    api_key = os.environ.get(
        "GEMINI_API_KEY"
    )

    if not api_key:
        raise RuntimeError(
            "No existe GEMINI_API_KEY."
        )

    return genai.Client(
        api_key=api_key
    )


def extract_json_from_response(text):
    text = text.strip()

    if text.startswith("```"):
        text = re.sub(
            r"^```(?:json)?",
            "",
            text,
            flags=re.IGNORECASE
        )

        text = re.sub(
            r"```$",
            "",
            text
        )

        text = text.strip()

    return json.loads(text)


def analyze_sections(article):
    print("Analizando secciones con Gemini...")

    prompt = load_prompt(
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

CONTENIDO:
{section["content"]}
""".strip()
        )

    sections_block = "\n\n".join(
        sections_text
    )

    prompt = prompt.replace(
        "{{ARTICLE_TITLE}}",
        article["title"]
    )

    prompt = prompt.replace(
        "{{ARTICLE_DATE}}",
        article["date"] or ""
    )

    prompt = prompt.replace(
        "{{ARTICLE_TYPE}}",
        article["type"]
    )

    prompt = prompt.replace(
        "{{SECTIONS}}",
        sections_block
    )

    client = get_gemini_client()

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )

    result = extract_json_from_response(
        response.text
    )

    if not isinstance(result, list):
        raise RuntimeError(
            "Gemini no devolvió una lista de análisis."
        )

    print(
        f"Gemini analizó {len(result)} secciones."
    )

    return result


# ============================================================
# QUEUE
# ============================================================

def create_queue(article, analysis):
    minimum_score = 75

    items = []

    sections = article["sections"]

    for index, result in enumerate(
        analysis
    ):
        if index >= len(sections):
            continue

        publication_type = result.get(
            "publication_type",
            "skip"
        )

        score = result.get(
            "publication_score",
            0
        )

        if publication_type != "standalone":
            continue

        if score < minimum_score:
            continue

        section = sections[index]

        items.append(
            {
                "article_url": article["url"],
                "article_title": article["title"],
                "article_date": article["date"],
                "article_type": article["type"],

                "title": result.get(
                    "title",
                    section["title"]
                ),

                "author": section["author"],
                "content": section["content"],
                "images": section["images"],

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

                "publication_score": score,

                "recommended": result.get(
                    "recommended",
                    False
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

    items.sort(
        key=lambda item: item.get(
            "publication_score",
            0
        ),
        reverse=True
    )

    for priority, item in enumerate(
        items,
        start=1
    ):
        item["priority"] = priority

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
            "minimum_publication_score": minimum_score,
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


def migrate_queue(queue):
    if not queue:
        return queue

    if "general_publication" not in queue:
        queue["general_publication"] = {
            "discord_posted": False,
            "discord_posted_at": None,
            "x_posted": False,
            "x_posted_at": None,
            "x_post_id": None
        }

    if "items" not in queue:
        queue["items"] = []

    for item in queue["items"]:

        item.setdefault(
            "published",
            False
        )

        item.setdefault(
            "published_at",
            None
        )

        item.setdefault(
            "platform",
            None
        )

        item.setdefault(
            "post_id",
            None
        )

        item.setdefault(
            "generated_text",
            None
        )

        item.setdefault(
            "generated_at",
            None
        )

        item.setdefault(
            "priority",
            0
        )

        item.setdefault(
            "images",
            []
        )

    return queue


def is_same_article(queue, article_url):
    if not queue:
        return False

    article = queue.get(
        "article",
        {}
    )

    return article.get(
        "url"
    ) == article_url


def get_next_pending_item(queue):
    pending = [
        item
        for item in queue.get(
            "items",
            []
        )
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
# LAST POSTS
# ============================================================

def get_last_published_posts(
    queue,
    limit=5
):
    published = [
        item
        for item in queue.get(
            "items",
            []
        )
        if item.get(
            "published",
            False
        )
        and item.get(
            "generated_text"
        )
    ]

    published.sort(
        key=lambda item: item.get(
            "published_at",
            ""
        ),
        reverse=True
    )

    posts = []

    for item in published[:limit]:
        posts.append(
            item["generated_text"]
        )

    if not posts:
        return (
            "No hay posts publicados "
            "anteriormente."
        )

    return "\n".join(
        f"{index}. {post}"
        for index, post in enumerate(
            posts,
            start=1
        )
    )


# ============================================================
# X POST GENERATION
# ============================================================

def generate_x_post(
    queue,
    item
):
    print("GENERANDO POST PARA X...")

    prompt = load_prompt(
        X_POST_PROMPT_FILE
    )

    prompt = prompt.replace(
        "{{ARTICLE_TITLE}}",
        item.get(
            "article_title",
            ""
        )
    )

    prompt = prompt.replace(
        "{{ARTICLE_DATE}}",
        item.get(
            "article_date",
            ""
        ) or ""
    )

    prompt = prompt.replace(
        "{{SECTION_TITLE}}",
        item.get(
            "title",
            ""
        )
    )

    prompt = prompt.replace(
        "{{AUTHOR}}",
        item.get(
            "author",
            ""
        )
    )

    prompt = prompt.replace(
        "{{CONTENT_TYPE}}",
        item.get(
            "content_type",
            "news"
        )
    )

    prompt = prompt.replace(
        "{{REASON}}",
        item.get(
            "reason",
            ""
        )
    )

    prompt = prompt.replace(
        "{{IMPORTANCE}}",
        str(
            item.get(
                "importance",
                0
            )
        )
    )

    prompt = prompt.replace(
        "{{INTERACTION_POTENTIAL}}",
        str(
            item.get(
                "interaction_potential",
                0
            )
        )
    )

    prompt = prompt.replace(
        "{{SOCIAL_VALUE}}",
        str(
            item.get(
                "social_value",
                0
            )
        )
    )

    prompt = prompt.replace(
        "{{LAST_POSTS}}",
        get_last_published_posts(
            queue
        )
    )

    prompt = prompt.replace(
        "{{CONTENT}}",
        item.get(
            "content",
            ""
        )
    )

    client = get_gemini_client()

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )

    result = extract_json_from_response(
        response.text
    )

    if not isinstance(result, dict):
        raise RuntimeError(
            "Gemini no devolvió un objeto JSON."
        )

    text = result.get(
        "text"
    )

    if not text:
        raise RuntimeError(
            "Gemini no devolvió el texto del post."
        )

    text = text.strip()

    if len(text) > 280:
        raise RuntimeError(
            f"El post supera los 280 caracteres: "
            f"{len(text)}"
        )

    print("POST GENERADO")
    print("----------------------------------------")
    print(text)
    print("----------------------------------------")

    return text


# ============================================================
# BUFFER
# ============================================================

def send_to_buffer(message):
    buffer_api_key = os.environ.get(
        "BUFFER_API_KEY"
    )

    buffer_channel_id = os.environ.get(
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
          }
        }

        ... on MutationError {
          message
        }
      }
    }
    """

    response = requests.post(
        "https://api.buffer.com",
        headers={
            "Content-Type": "application/json",
            "Authorization": (
                f"Bearer {buffer_api_key}"
            )
        },
        json={
            "query": query,
            "variables": {
                "input": {
                    "text": message,
                    "channelId": buffer_channel_id,
                    "schedulingType": "automatic",
                    "mode": "shareNow"
                }
            }
        },
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    if "errors" in data:
        raise RuntimeError(
            data["errors"]
        )

    if "data" not in data:
        raise RuntimeError(
            "Buffer no devolvió data."
        )

    result = data["data"].get(
        "createPost"
    )

    if not result:
        raise RuntimeError(
            "Buffer no devolvió createPost."
        )

    if "message" in result:
        raise RuntimeError(
            result["message"]
        )

    post = result.get(
        "post"
    )

    if not post:
        raise RuntimeError(
            "Buffer no devolvió el post creado."
        )

    print(
        "✅ Message sent to X via Buffer."
    )

    print(
        f"Buffer post ID: "
        f"{post.get('id')}"
    )

    return post


# ============================================================
# PUBLISH NEXT CONTENT
# ============================================================

def publish_next_content(queue):
    print("")
    print("========================================")
    print("SIGUIENTE CONTENIDO PENDIENTE")
    print("========================================")

    item = get_next_pending_item(
        queue
    )

    if not item:
        print(
            "No hay contenido pendiente."
        )
        return

    print(
        f"Priority: "
        f"{item.get('priority')}"
    )

    print(
        f"Título: "
        f"{item.get('title')}"
    )

    print(
        f"Score: "
        f"{item.get('publication_score')}"
    )

    print(
        f"Tipo: "
        f"{item.get('content_type')}"
    )

    generated_text = generate_x_post(
        queue,
        item
    )

    print("")
    print("ENVIANDO A BUFFER...")

    try:
        post = send_to_buffer(
            generated_text
        )

    except Exception as error:
        print("")
        print(
            "❌ ERROR EN BUFFER"
        )
        print(
            str(error)
        )
        print("")
        print(
            "El contenido NO será marcado "
            "como publicado."
        )
        print(
            "Quedará pendiente para el "
            "próximo ciclo."
        )

        raise

    # --------------------------------------------------------
    # IMPORTANTE:
    # SOLO MARCAMOS COMO PUBLICADO DESPUÉS
    # DE QUE BUFFER CONFIRMÓ EL POST.
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

    print("")
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
        f"Post ID: "
        f"{item.get('post_id')}"
    )

    print(
        f"Publicado: "
        f"{item.get('published_at')}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print("========================================")
    print("CALAVERA RUST NEWS")
    print("========================================")
    print("")

    # --------------------------------------------------------
    # GET LATEST ARTICLE
    # --------------------------------------------------------

    latest_url = get_latest_news()

    print(
        f"Último artículo detectado:"
    )

    print(latest_url)

    # --------------------------------------------------------
    # LOAD CURRENT QUEUE
    # --------------------------------------------------------

    queue = load_json(
        QUEUE_FILE,
        None
    )

    queue = migrate_queue(
        queue
    )

    # --------------------------------------------------------
    # NEW ARTICLE
    # --------------------------------------------------------

    if not is_same_article(
        queue,
        latest_url
    ):

        print("")
        print(
            "🆕 NUEVO PATCH DETECTADO"
        )

        print(
            "Parseando artículo..."
        )

        article = parse_article(
            latest_url
        )

        print(
            "Analizando contenido..."
        )

        analysis = analyze_sections(
            article
        )

        print(
            "Creando cola de contenido..."
        )

        queue = create_queue(
            article,
            analysis
        )

        save_json(
            NEWS_ANALYSIS_FILE,
            {
                "article": article,
                "analysis": analysis
            }
        )

        save_json(
            QUEUE_FILE,
            queue
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

        print("")
        print(
            "========================================"
        )

        print(
            "NUEVA COLA CREADA"
        )

        print(
            "========================================"
        )

        print(
            f"Patch: "
            f"{article['title']}"
        )

        print(
            f"Secciones analizadas: "
            f"{len(article['sections'])}"
        )

        print(
            f"Secciones seleccionadas: "
            f"{len(queue['items'])}"
        )

        print("")
        print(
            "El contenido específico NO se "
            "publicará en esta ejecución."
        )

        print(
            "Primero queda preparada la cola "
            "del nuevo patch."
        )

        return

    # --------------------------------------------------------
    # EXISTING ARTICLE
    # --------------------------------------------------------

    print("")
    print(
        "♻️ PATCH ACTUAL YA ESTÁ EN COLA"
    )

    print(
        f"Patch: "
        f"{queue['article'].get('title')}"
    )

    general = queue.get(
        "general_publication",
        {}
    )

    print(
        f"Discord general publicado: "
        f"{general.get('discord_posted', False)}"
    )

    print(
        f"X general publicado: "
        f"{general.get('x_posted', False)}"
    )

    # --------------------------------------------------------
    # PUBLISH ONE SECTION
    # --------------------------------------------------------

    publish_next_content(
        queue
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
