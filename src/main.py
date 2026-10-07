import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from google import genai


BASE_URL = "https://rust.facepunch.com"
NEWS_URL = f"{BASE_URL}/news/"

GEMINI_MODEL = "gemini-3.5-flash-lite"

DATA_DIR = "data"
LATEST_NEWS_FILE = os.path.join(DATA_DIR, "latest_news.json")
ANALYSIS_FILE = os.path.join(DATA_DIR, "news_analysis.json")
QUEUE_FILE = os.path.join(DATA_DIR, "content_queue.json")

ANALYZE_PROMPT_FILE = "prompt/analyze_devblog_sections.txt"
X_POST_PROMPT_FILE = "prompt/generate_x_post.txt"
GENERAL_ANNOUNCEMENT_PROMPT_FILE = (
    "prompt/generate_general_announcement.txt"
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
BUFFER_API_KEY = os.getenv("BUFFER_API_KEY")
BUFFER_CHANNEL_ID = os.getenv("BUFFER_CHANNEL_ID")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")


# ============================================================
# UTILIDADES
# ============================================================

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def load_json(path, default=None):
    if not os.path.exists(path):
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    ensure_data_dir()

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


def read_prompt(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def extract_json(text):
    text = text.strip()

    if text.startswith("```"):
        text = re.sub(
            r"^```(?:json)?",
            "",
            text
        )

        text = re.sub(
            r"```$",
            "",
            text
        )

        text = text.strip()

    return json.loads(text)


# ============================================================
# GEMINI
# ============================================================

def get_gemini_client():
    if not GEMINI_API_KEY:
        raise RuntimeError(
            "Falta GEMINI_API_KEY"
        )

    return genai.Client(
        api_key=GEMINI_API_KEY
    )


def ask_gemini(prompt):
    client = get_gemini_client()

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )

    if not response.text:
        raise RuntimeError(
            "Gemini devolvió una respuesta vacía"
        )

    return response.text.strip()


# ============================================================
# SCRAPER
# ============================================================

def get_latest_news():
    print(
        "Consultando noticias de Rust..."
    )

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

        url = urljoin(
            BASE_URL,
            href
        )

        print(
            f"Última noticia detectada: {url}"
        )

        return url

    raise RuntimeError(
        "No se pudo encontrar la última noticia"
    )


def scrape_article(url):
    print(
        f"Scrapeando artículo: {url}"
    )

    response = requests.get(
        url,
        timeout=30
    )

    response.raise_for_status()

    html = response.text

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    # --------------------------------------------------------
    # METADATA
    # --------------------------------------------------------

    html_title = (
        soup.title.get_text(
            " ",
            strip=True
        )
        if soup.title
        else ""
    )

    article_title = html_title

    if article_title.endswith(
        " - News - Rust"
    ):
        article_title = article_title[
            :-len(" - News - Rust")
        ].strip()

    date_patterns = [
        r"\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b",
        r"\b\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\b",
        r"\b[A-Za-z]+\s+\d{1,2},\s+\d{4}\b"
    ]

    article_date = None

    for pattern in date_patterns:
        match = re.search(
            pattern,
            html
        )

        if match:
            article_date = match.group(0)
            break

    article_type = "DEVBLOG"

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

        if not title:
            continue

        if title.strip() == "⠀":
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

        for img in content_element.select(
            "img"
        ):
            src = img.get("src")

            if not src:
                continue

            image_url = urljoin(
                BASE_URL,
                src
            )

            if image_url not in images:
                images.append(image_url)

        sections.append({
            "title": title,
            "author": author,
            "content": content,
            "images": images
        })

    print()
    print("DEBUG metadata:")
    print(
        f"HTML title: {html_title}"
    )
    print(
        "h1: NO ENCONTRADO"
    )
    print(
        f"Fecha detectada: {article_date}"
    )
    print(
        f"Tipo detectado: {article_type}"
    )
    print(
        f"Secciones encontradas: {len(sections)}"
    )
    print(
        f"Título detectado: {article_title}"
    )

    return {
        "url": url,
        "title": article_title,
        "date": article_date,
        "type": article_type,
        "sections": sections
    }


# ============================================================
# ANALISIS DEL DEVBLOG
# ============================================================

def analyze_sections(article):
    prompt_template = read_prompt(
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

Título:
{section["title"]}

Autor:
{section["author"]}

Contenido:
{section["content"]}
""".strip()
        )

    sections_text = "\n\n".join(
        sections_text
    )

    prompt = (
        prompt_template
        .replace(
            "{{ARTICLE_TITLE}}",
            article["title"]
        )
        .replace(
            "{{ARTICLE_DATE}}",
            article["date"] or ""
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

    print()
    print(
        "Analizando secciones con Gemini..."
    )

    raw = ask_gemini(
        prompt
    )

    analysis = extract_json(
        raw
    )

    if not isinstance(
        analysis,
        list
    ):
        raise RuntimeError(
            "Gemini no devolvió una lista de análisis"
        )

    return analysis


# ============================================================
# ULTIMOS POSTS
# ============================================================

def get_last_posts(
    queue,
    limit=10
):
    posts = []

    for item in queue.get(
        "items",
        []
    ):
        generated_text = item.get(
            "generated_text"
        )

        if generated_text:
            posts.append({
                "title": item.get(
                    "title"
                ),
                "text": generated_text
            })

    return posts[-limit:]


def format_last_posts(posts):
    if not posts:
        return (
            "No hay posts publicados anteriormente."
        )

    result = []

    for index, post in enumerate(
        posts,
        start=1
    ):
        result.append(
            f"""
POST {index}

Sección:
{post["title"]}

Texto:
{post["text"]}
""".strip()
        )

    return "\n\n".join(
        result
    )


# ============================================================
# CREAR COLA
# ============================================================

def build_content_queue(
    article,
    analysis
):
    minimum_score = 75

    analysis_by_title = {
        item.get("title"): item
        for item in analysis
        if item.get("title")
    }

    queue_items = []

    priority = 1

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

        score = int(
            result.get(
                "publication_score",
                0
            )
        )

        if publication_type != "standalone":
            continue

        if score < minimum_score:
            continue

        queue_items.append({
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

            "priority": priority
        })

        priority += 1

    queue = {
        "article": {
            "url": article["url"],
            "title": article["title"],
            "date": article["date"],
            "type": article["type"]
        },

        "general_publication": {
            "generated": False,

            "x_text": None,
            "discord_text": None,

            "x_posted": False,
            "x_posted_at": None,
            "x_post_id": None,

            "discord_posted": False,
            "discord_posted_at": None,

            "generated_at": None
        },

        "selection": {
            "minimum_publication_score": minimum_score,
            "total_sections": len(
                article["sections"]
            ),
            "selected_sections": len(
                queue_items
            )
        },

        "items": queue_items
    }

    return queue


# ============================================================
# ANUNCIO GENERAL
# ============================================================

def generate_general_announcement(
    queue
):
    prompt_template = read_prompt(
        GENERAL_ANNOUNCEMENT_PROMPT_FILE
    )

    article = queue["article"]

    selected_sections = []

    for item in queue["items"]:
        selected_sections.append(
            f"""
Título:
{item["title"]}

Score:
{item["publication_score"]}

Tipo:
{item["content_type"]}

Contenido:
{item["content"]}
""".strip()
        )

    sections_text = "\n\n".join(
        selected_sections
    )

    last_posts = get_last_posts(
        queue
    )

    prompt = (
        prompt_template
        .replace(
            "{{ARTICLE_TITLE}}",
            article["title"]
        )
        .replace(
            "{{ARTICLE_DATE}}",
            article.get("date") or ""
        )
        .replace(
            "{{ARTICLE_TYPE}}",
            article.get("type") or ""
        )
        .replace(
            "{{LAST_POSTS}}",
            format_last_posts(
                last_posts
            )
        )
        .replace(
            "{{SECTIONS}}",
            sections_text
        )
    )

    print()
    print(
        "Generando anuncio general..."
    )

    raw = ask_gemini(
        prompt
    )

    result = extract_json(
        raw
    )

    x_text = result.get(
        "x_text"
    )

    discord_text = result.get(
        "discord_text"
    )

    if not x_text:
        raise RuntimeError(
            "El anuncio general no contiene x_text"
        )

    if not discord_text:
        raise RuntimeError(
            "El anuncio general no contiene discord_text"
        )

    return {
        "x_text": x_text,
        "discord_text": discord_text
    }


# ============================================================
# BUFFER
# ============================================================

def buffer_create_post(
    text,
    image_url=None
):
    if not BUFFER_API_KEY:
        raise RuntimeError(
            "Falta BUFFER_API_KEY"
        )

    if not BUFFER_CHANNEL_ID:
        raise RuntimeError(
            "Falta BUFFER_CHANNEL_ID"
        )

    mutation = """
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
        "text": text,
        "channelId": BUFFER_CHANNEL_ID,

        # Publicar inmediatamente
        "mode": "shareNow",

        # Buffer maneja automáticamente
        # la publicación
        "schedulingType": "automatic"
    }

    if image_url:
        input_data["assets"] = [
            {
                "image": {
                    "url": image_url
                }
            }
        ]

    response = requests.post(
        "https://api.buffer.com",
        headers={
            "Authorization": (
                f"Bearer {BUFFER_API_KEY}"
            ),
            "Content-Type": "application/json"
        },
        json={
            "query": mutation,
            "variables": {
                "input": input_data
            }
        },
        timeout=30
    )

    response.raise_for_status()

    data = response.json()

    if data.get("errors"):
        raise RuntimeError(
            f"Buffer GraphQL error: "
            f"{data['errors']}"
        )

    create_post = (
        data
        .get("data", {})
        .get("createPost")
    )

    if not create_post:
        raise RuntimeError(
            f"Buffer no devolvió createPost: "
            f"{data}"
        )

    post = create_post.get(
        "post"
    )

    if post:
        return post

    message = create_post.get(
        "message"
    )

    if message:
        raise RuntimeError(
            f"Buffer rechazó el post: "
            f"{message}"
        )

    raise RuntimeError(
        f"Respuesta inesperada de Buffer: "
        f"{data}"
    )


# ============================================================
# DISCORD
# ============================================================

def publish_discord(text):
    if not DISCORD_WEBHOOK_URL:
        raise RuntimeError(
            "Falta DISCORD_WEBHOOK_URL"
        )

    response = requests.post(
        DISCORD_WEBHOOK_URL,
        json={
            "content": text
        },
        timeout=30
    )

    response.raise_for_status()

    return True


# ============================================================
# PROCESAR ANUNCIO GENERAL
# ============================================================

def process_general_announcement(
    queue
):
    publication = queue.setdefault(
        "general_publication",
        {
            "generated": False,
            "x_text": None,
            "discord_text": None,

            "x_posted": False,
            "x_posted_at": None,
            "x_post_id": None,

            "discord_posted": False,
            "discord_posted_at": None,

            "generated_at": None
        }
    )

    # --------------------------------------------------------
    # GENERAR UNA SOLA VEZ
    # --------------------------------------------------------

    if not publication.get(
        "generated"
    ):
        result = generate_general_announcement(
            queue
        )

        publication["x_text"] = result[
            "x_text"
        ]

        publication["discord_text"] = result[
            "discord_text"
        ]

        publication["generated"] = True
        publication["generated_at"] = now_iso()

        save_json(
            QUEUE_FILE,
            queue
        )

        print()
        print(
            "ANUNCIO GENERAL - X"
        )
        print()
        print(
            publication["x_text"]
        )

        print()
        print(
            "ANUNCIO GENERAL - DISCORD"
        )
        print()
        print(
            publication["discord_text"]
        )

    # --------------------------------------------------------
    # PUBLICAR X
    # --------------------------------------------------------

    if not publication.get(
        "x_posted"
    ):
        print()
        print(
            "Publicando anuncio general "
            "en X mediante Buffer..."
        )

        post = buffer_create_post(
            publication["x_text"]
        )

        publication["x_posted"] = True
        publication["x_posted_at"] = now_iso()
        publication["x_post_id"] = post.get(
            "id"
        )

        save_json(
            QUEUE_FILE,
            queue
        )

        print(
            "Anuncio general publicado "
            f"en X. ID: {post.get('id')}"
        )

    # --------------------------------------------------------
    # PUBLICAR DISCORD
    # --------------------------------------------------------

    if not publication.get(
        "discord_posted"
    ):
        print()
        print(
            "Publicando anuncio general "
            "en Discord..."
        )

        publish_discord(
            publication["discord_text"]
        )

        publication["discord_posted"] = True
        publication["discord_posted_at"] = now_iso()

        save_json(
            QUEUE_FILE,
            queue
        )

        print(
            "Anuncio general publicado "
            "en Discord."
        )

    return (
        publication.get(
            "x_posted",
            False
        )
        and publication.get(
            "discord_posted",
            False
        )
    )


# ============================================================
# GENERAR POST DE SECCION
# ============================================================

def generate_x_post(
    queue,
    item
):
    prompt_template = read_prompt(
        X_POST_PROMPT_FILE
    )

    article = queue["article"]

    last_posts = get_last_posts(
        queue
    )

    prompt = (
        prompt_template
        .replace(
            "{{ARTICLE_TITLE}}",
            article["title"]
        )
        .replace(
            "{{ARTICLE_DATE}}",
            article.get("date") or ""
        )
        .replace(
            "{{ARTICLE_TYPE}}",
            article.get("type") or ""
        )
        .replace(
            "{{LAST_POSTS}}",
            format_last_posts(
                last_posts
            )
        )
        .replace(
            "{{SECTION_TITLE}}",
            item["title"]
        )
        .replace(
            "{{SECTION_CONTENT}}",
            item["content"]
        )
    )

    print()
    print(
        f"Generando post X para: "
        f"{item['title']}"
    )

    raw = ask_gemini(
        prompt
    )

    result = extract_json(
        raw
    )

    text = (
        result.get("text")
        or result.get("x_text")
    )

    if not text:
        raise RuntimeError(
            "Gemini no devolvió texto "
            "para el post X"
        )

    print()
    print(
        "Post generado:"
    )
    print(text)

    return text


# ============================================================
# IMAGEN
# ============================================================

def get_first_valid_image(
    item
):
    images = item.get(
        "images"
    ) or []

    for image_url in images:
        if not image_url:
            continue

        try:
            response = requests.head(
                image_url,
                timeout=15,
                allow_redirects=True
            )

            if response.status_code < 400:
                return image_url

        except Exception:
            continue

    return None


# ============================================================
# PUBLICAR SIGUIENTE CONTENIDO
# ============================================================

def publish_next_content(
    queue
):
    items = queue.get(
        "items",
        []
    )

    unpublished = [
        item
        for item in items
        if not item.get(
            "published",
            False
        )
    ]

    if not unpublished:
        print()
        print(
            "No quedan secciones pendientes "
            "para publicar."
        )

        return False

    unpublished.sort(
        key=lambda item: item.get(
            "priority",
            999
        )
    )

    item = unpublished[0]

    print()
    print(
        "Próximo contenido:"
    )

    print(
        f"Título: {item['title']}"
    )

    print(
        f"Score: "
        f"{item['publication_score']}"
    )

    print(
        f"Prioridad: "
        f"{item['priority']}"
    )

    # --------------------------------------------------------
    # GENERAR
    # --------------------------------------------------------

    generated_text = generate_x_post(
        queue,
        item
    )

    # --------------------------------------------------------
    # BUSCAR IMAGEN
    # --------------------------------------------------------

    image_url = get_first_valid_image(
        item
    )

    if image_url:
        print()
        print(
            "Imagen encontrada:"
        )
        print(image_url)

    else:
        print()
        print(
            "No se encontró una imagen válida."
        )

    # --------------------------------------------------------
    # PUBLICAR
    # --------------------------------------------------------

    print()
    print(
        "Publicando mediante Buffer..."
    )

    post = buffer_create_post(
        generated_text,
        image_url=image_url
    )

    post_id = post.get(
        "id"
    )

    print(
        "Publicado correctamente "
        f"en Buffer. ID: {post_id}"
    )

    # --------------------------------------------------------
    # MARCAR SOLO DESPUES DEL EXITO
    # --------------------------------------------------------

    item["published"] = True
    item["published_at"] = now_iso()
    item["platform"] = "x"
    item["post_id"] = post_id
    item["generated_text"] = generated_text
    item["generated_at"] = now_iso()

    save_json(
        QUEUE_FILE,
        queue
    )

    print(
        "Estado guardado correctamente."
    )

    return True


# ============================================================
# MAIN
# ============================================================

def main():
    ensure_data_dir()

    latest_news = load_json(
        LATEST_NEWS_FILE,
        {}
    )

    queue = load_json(
        QUEUE_FILE,
        {}
    )

    latest_url = get_latest_news()

    # ========================================================
    # NUEVO ARTICULO
    # ========================================================

    current_article_url = (
        queue
        .get("article", {})
        .get("url")
    )

    if current_article_url != latest_url:
        print()
        print(
            "Nuevo artículo detectado."
        )

        print(
            latest_url
        )

        article = scrape_article(
            latest_url
        )

        analysis = analyze_sections(
            article
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

        save_json(
            ANALYSIS_FILE,
            analysis
        )

        queue = build_content_queue(
            article,
            analysis
        )

        save_json(
            QUEUE_FILE,
            queue
        )

        print()
        print(
            "Cola de contenido creada."
        )

        print(
            "Secciones seleccionadas: "
            f"{len(queue['items'])}"
        )

        # ----------------------------------------------------
        # DIA 1
        # SOLO ANUNCIO GENERAL
        # ----------------------------------------------------

        general_complete = (
            process_general_announcement(
                queue
            )
        )

        if general_complete:
            print()
            print(
                "Anuncio general completado."
            )

        print()
        print(
            "La primera sección queda "
            "para la próxima ejecución."
        )

        return

    # ========================================================
    # ARTICULO YA PROCESADO
    # ========================================================

    print()
    print(
        "Patch ya procesado."
    )

    if not queue:
        print(
            "No existe una cola válida."
        )

        return

    # ========================================================
    # COMPLETAR ANUNCIO GENERAL
    # ========================================================

    publication = queue.get(
        "general_publication",
        {}
    )

    general_complete = (
        publication.get(
            "x_posted",
            False
        )
        and publication.get(
            "discord_posted",
            False
        )
    )

    if not general_complete:
        print()
        print(
            "El anuncio general todavía "
            "no está completo."
        )

        completed_now = (
            process_general_announcement(
                queue
            )
        )

        if completed_now:
            print()
            print(
                "Anuncio general completado."
            )

            print(
                "La primera sección queda "
                "para la próxima ejecución."
            )

        return

    # ========================================================
    # CONTENIDO DIARIO
    # ========================================================

    publish_next_content(
        queue
    )


if __name__ == "__main__":
    main()
