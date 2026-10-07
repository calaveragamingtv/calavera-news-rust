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

DATA_DIR = "data"

LATEST_NEWS_FILE = os.path.join(
    DATA_DIR,
    "latest_news.json"
)

NEWS_ANALYSIS_FILE = os.path.join(
    DATA_DIR,
    "news_analysis.json"
)

QUEUE_FILE = os.path.join(
    DATA_DIR,
    "content_queue.json"
)

ANALYZE_PROMPT_FILE = os.path.join(
    "prompt",
    "analyze_devblog_sections.txt"
)

GENERATE_X_PROMPT_FILE = os.path.join(
    "prompt",
    "generate_x_post.txt"
)

GEMINI_MODEL = "gemini-3.5-flash-lite"

MINIMUM_PUBLICATION_SCORE = 75


# ============================================================
# UTILIDADES JSON
# ============================================================

def load_json(path, default=None):
    if not os.path.exists(path):
        return default

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(
        os.path.dirname(path),
        exist_ok=True
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


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

    array_match = re.search(
        r"\[.*\]",
        text,
        flags=re.DOTALL
    )

    if array_match:
        return json.loads(
            array_match.group(0)
        )

    object_match = re.search(
        r"\{.*\}",
        text,
        flags=re.DOTALL
    )

    if object_match:
        return json.loads(
            object_match.group(0)
        )

    raise ValueError(
        "Gemini no devolvió JSON válido."
    )


# ============================================================
# SCRAPER
# ============================================================

def get_latest_news():
    response = requests.get(
        NEWS_URL,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
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

        return urljoin(
            BASE_URL,
            href
        )

    raise RuntimeError(
        "No se pudo detectar el último artículo."
    )


# ============================================================
# PARSER DEL DEVBLOG
# ============================================================

def parse_news(url):
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
    # TÍTULO
    # --------------------------------------------------------

    title = ""

    if soup.title:
        title = soup.title.get_text(
            " ",
            strip=True
        )

        title = re.sub(
            r"\s*-\s*News\s*-\s*Rust\s*$",
            "",
            title,
            flags=re.IGNORECASE
        ).strip()

    # --------------------------------------------------------
    # FECHA
    # --------------------------------------------------------

    date = None

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
            date = match.group(0)
            break

    # --------------------------------------------------------
    # TIPO
    # --------------------------------------------------------

    article_type = "DEVBLOG"

    if "devblog" not in full_text.lower():
        article_type = "NEWS"

    # --------------------------------------------------------
    # SECCIONES
    # --------------------------------------------------------

    sections = []

    blocks = soup.select(
        ".news-section-block"
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

        if not title_element:
            continue

        section_title = title_element.get_text(
            " ",
            strip=True
        ).strip()

        if not section_title:
            continue

        if section_title == "⠀":
            continue

        author_element = header.select_one(
            ".author"
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

        if not content_element:
            continue

        content = content_element.get_text(
            "\n",
            strip=True
        )

        images = []

        for img in content_element.select("img"):
            src = img.get("src")

            if not src:
                continue

            images.append(
                urljoin(
                    BASE_URL,
                    src
                )
            )

        if not content:
            continue

        sections.append(
            {
                "title": section_title,
                "author": author,
                "content": content,
                "images": images
            }
        )

    print("DEBUG metadata:")
    print(
        f"HTML title: "
        f"{soup.title.get_text(strip=True) if soup.title else 'NO ENCONTRADO'}"
    )
    print(
        "h1: "
        f"{soup.find('h1').get_text(strip=True) if soup.find('h1') else 'NO ENCONTRADO'}"
    )
    print(
        f"time: "
        f"{soup.find('time').get_text(strip=True) if soup.find('time') else 'NO ENCONTRADO'}"
    )
    print(
        f"DEVBLOG links: "
        f"{len(soup.select('a[href*=\"/news/\"]'))}"
    )
    print(
        f"Secciones encontradas: "
        f"{len(sections)}"
    )
    print(
        f"Título detectado: {title}"
    )
    print(
        f"Fecha detectada: {date}"
    )
    print(
        f"Tipo detectado: {article_type}"
    )

    return {
        "url": url,
        "title": title,
        "date": date,
        "type": article_type,
        "sections": sections
    }


# ============================================================
# ANÁLISIS GEMINI
# ============================================================

def analyze_sections(article):
    if not os.path.exists(
        ANALYZE_PROMPT_FILE
    ):
        raise RuntimeError(
            f"No existe {ANALYZE_PROMPT_FILE}"
        )

    with open(
        ANALYZE_PROMPT_FILE,
        "r",
        encoding="utf-8"
    ) as f:
        prompt = f.read()

    sections_text = []

    for index, section in enumerate(
        article["sections"],
        start=1
    ):
        sections_text.append(
            f"""
SECTION {index}

TITLE:
{section["title"]}

AUTHOR:
{section["author"]}

CONTENT:
{section["content"]}
"""
        )

    prompt = prompt.replace(
        "{{ARTICLE_TITLE}}",
        article["title"]
    )

    prompt = prompt.replace(
        "{{ARTICLE_DATE}}",
        str(article["date"])
    )

    prompt = prompt.replace(
        "{{ARTICLE_TYPE}}",
        article["type"]
    )

    prompt = prompt.replace(
        "{{SECTIONS}}",
        "\n".join(sections_text)
    )

    client = get_gemini_client()

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )

    result = extract_json_from_response(
        response.text
    )

    if not isinstance(
        result,
        list
    ):
        raise ValueError(
            "El análisis de Gemini no devolvió una lista."
        )

    return result


# ============================================================
# CREAR COLA
# ============================================================

def create_content_queue(
    article,
    analysis
):
    analysis_by_title = {
        item.get("title"): item
        for item in analysis
    }

    selected_items = []

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

        score = result.get(
            "publication_score",
            0
        )

        if publication_type != "standalone":
            continue

        if score < MINIMUM_PUBLICATION_SCORE:
            continue

        selected_items.append(
            {
                "article_url": article["url"],
                "article_title": article["title"],
                "article_date": article["date"],
                "article_type": article["type"],

                "title": section["title"],
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

    selected_items.sort(
        key=lambda item: (
            item["publication_score"],
            item["importance"],
            item["social_value"],
            item["interaction_potential"]
        ),
        reverse=True
    )

    for index, item in enumerate(
        selected_items,
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
                len(selected_items)
        },

        "items": selected_items
    }

    return queue


# ============================================================
# MIGRACIÓN DE COLA ANTIGUA
# ============================================================

def migrate_queue_if_needed():
    queue = load_json(
        QUEUE_FILE
    )

    if not queue:
        return None

    if (
        isinstance(queue, dict)
        and "article" in queue
        and "items" in queue
    ):
        return queue

    print(
        "⚠️ Cola antigua detectada."
    )

    print(
        "Migrando content_queue.json..."
    )

    old_items = []

    if isinstance(queue, list):
        old_items = queue

    elif isinstance(queue, dict):
        old_items = queue.get(
            "items",
            []
        )

    article = {}

    if old_items:
        first = old_items[0]

        article = {
            "url": first.get(
                "article_url",
                ""
            ),
            "title": first.get(
                "article_title",
                ""
            ),
            "date": first.get(
                "article_date"
            ),
            "type": first.get(
                "article_type",
                "DEVBLOG"
            )
        }

    new_items = []

    for index, item in enumerate(
        old_items,
        start=1
    ):
        new_item = dict(item)

        new_item.setdefault(
            "published",
            False
        )

        new_item.setdefault(
            "published_at",
            None
        )

        new_item.setdefault(
            "platform",
            None
        )

        new_item.setdefault(
            "post_id",
            None
        )

        new_item.setdefault(
            "generated_text",
            None
        )

        new_item.setdefault(
            "generated_at",
            None
        )

        new_item.setdefault(
            "priority",
            index
        )

        new_items.append(
            new_item
        )

    new_queue = {
        "article": article,

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
                len(new_items),

            "selected_sections":
                len(new_items)
        },

        "items": new_items
    }

    save_json(
        QUEUE_FILE,
        new_queue
    )

    print(
        "✅ Migración completada."
    )

    return new_queue


# ============================================================
# COMPARAR ARTÍCULO
# ============================================================

def is_new_article(
    latest_url,
    queue
):
    if not queue:
        return True

    article = queue.get(
        "article",
        {}
    )

    stored_url = article.get(
        "url"
    )

    return stored_url != latest_url


# ============================================================
# SIGUIENTE CONTENIDO
# ============================================================

def get_next_pending_item(queue):
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
            9999
        )
    )

    return pending[0]


# ============================================================
# ÚLTIMOS POSTS PUBLICADOS
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
# GENERAR POST PARA X
# ============================================================

def generate_x_post(
    queue,
    item
):
    if not os.path.exists(
        GENERATE_X_PROMPT_FILE
    ):
        raise RuntimeError(
            f"No existe {GENERATE_X_PROMPT_FILE}"
        )

    with open(
        GENERATE_X_PROMPT_FILE,
        "r",
        encoding="utf-8"
    ) as f:
        prompt = f.read()

    last_posts = get_last_published_posts(
        queue
    )

    replacements = {
        "{{ARTICLE_TITLE}}":
            item.get(
                "article_title",
                ""
            ),

        "{{ARTICLE_DATE}}":
            str(
                item.get(
                    "article_date",
                    ""
                )
            ),

        "{{SECTION_TITLE}}":
            item.get(
                "title",
                ""
            ),

        "{{AUTHOR}}":
            item.get(
                "author",
                ""
            ),

        "{{CONTENT_TYPE}}":
            item.get(
                "content_type",
                "news"
            ),

        "{{REASON}}":
            item.get(
                "reason",
                ""
            ),

        "{{IMPORTANCE}}":
            str(
                item.get(
                    "importance",
                    0
                )
            ),

        "{{INTERACTION_POTENTIAL}}":
            str(
                item.get(
                    "interaction_potential",
                    0
                )
            ),

        "{{SOCIAL_VALUE}}":
            str(
                item.get(
                    "social_value",
                    0
                )
            ),

        "{{LAST_POSTS}}":
            last_posts,

        "{{CONTENT}}":
            item.get(
                "content",
                ""
            )
    }

    for placeholder, value in replacements.items():
        prompt = prompt.replace(
            placeholder,
            value
        )

    client = get_gemini_client()

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )

    result = extract_json_from_response(
        response.text
    )

    if not isinstance(
        result,
        dict
    ):
        raise ValueError(
            "Gemini no devolvió un objeto JSON."
        )

    generated_text = result.get(
        "text",
        ""
    ).strip()

    if not generated_text:
        raise ValueError(
            "Gemini devolvió un post vacío."
        )

    if len(generated_text) > 280:
        raise ValueError(
            f"El post generado tiene "
            f"{len(generated_text)} caracteres."
        )

    return generated_text


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
            "Authorization":
                f"Bearer {buffer_api_key}",
        },
        json={
            "query": query,
            "variables": {
                "input": {
                    "text": message,
                    "channelId":
                        buffer_channel_id,
                    "schedulingType":
                        "automatic",
                    "mode":
                        "shareNow"
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

    result = data[
        "data"
    ][
        "createPost"
    ]

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

    return post


# ============================================================
# PUBLICAR SIGUIENTE CONTENIDO
# ============================================================

def publish_next_content(queue):

    item = get_next_pending_item(
        queue
    )

    if not item:
        print()
        print(
            "✅ No quedan contenidos pendientes."
        )
        print(
            "Esperando un nuevo patch."
        )
        return

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
        f"Priority: {item.get('priority')}"
    )

    print(
        f"Título: {item.get('title')}"
    )

    print(
        f"Score: {item.get('publication_score')}"
    )

    print(
        f"Tipo: {item.get('content_type')}"
    )

    print()

    print(
        "GENERANDO POST PARA X..."
    )

    generated_text = generate_x_post(
        queue,
        item
    )

    print()
    print(
        "POST GENERADO"
    )

    print(
        "----------------------------------------"
    )

    print(
        generated_text
    )

    print(
        "----------------------------------------"
    )

    # ========================================================
    # MODO PRUEBA
    # ========================================================

    print()
    print(
        "⚠️ MODO PRUEBA"
    )

    print(
        "El post NO será enviado a Buffer."
    )

    print(
        "El contenido NO será marcado como publicado."
    )

    print()


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

    os.makedirs(
        DATA_DIR,
        exist_ok=True
    )

    # --------------------------------------------------------
    # Detectar último artículo
    # --------------------------------------------------------

    latest_url = get_latest_news()

    print()
    print(
        "Último artículo detectado:"
    )

    print(
        latest_url
    )

    # --------------------------------------------------------
    # Cargar / migrar cola
    # --------------------------------------------------------

    queue = migrate_queue_if_needed()

    # --------------------------------------------------------
    # Nuevo artículo
    # --------------------------------------------------------

    if is_new_article(
        latest_url,
        queue
    ):

        print()
        print(
            "🆕 NUEVO PATCH DETECTADO"
        )

        print()
        print(
            "Analizando artículo..."
        )

        article = parse_news(
            latest_url
        )

        print()
        print(
            "Analizando secciones con Gemini..."
        )

        analysis = analyze_sections(
            article
        )

        save_json(
            NEWS_ANALYSIS_FILE,
            analysis
        )

        queue = create_content_queue(
            article,
            analysis
        )

        save_json(
            QUEUE_FILE,
            queue
        )

        save_json(
            LATEST_NEWS_FILE,
            article
        )

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
            f"Patch: {article['title']}"
        )

        print(
            f"Secciones totales: "
            f"{len(article['sections'])}"
        )

        print(
            f"Secciones seleccionadas: "
            f"{len(queue['items'])}"
        )

        print()
        print(
            "⚠️ Hoy solamente se creó la cola."
        )

        print(
            "El anuncio general de Discord/X "
            "se implementará después."
        )

        print(
            "No se publica todavía contenido "
            "individual."
        )

        return

    # --------------------------------------------------------
    # Patch existente
    # --------------------------------------------------------

    print()
    print(
        "♻️ PATCH ACTUAL YA ESTÁ EN COLA"
    )

    print(
        f"Patch: "
        f"{queue['article'].get('title')}"
    )

    print(
        "Discord general publicado: "
        f"{queue['general_publication'].get('discord_posted')}"
    )

    print(
        "X general publicado: "
        f"{queue['general_publication'].get('x_posted')}"
    )

    # --------------------------------------------------------
    # Publicar siguiente contenido
    # --------------------------------------------------------

    publish_next_content(
        queue
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
