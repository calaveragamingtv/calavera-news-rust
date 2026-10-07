import os
import re
import json
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from google import genai


BASE_URL = "https://rust.facepunch.com"
NEWS_URL = f"{BASE_URL}/news/"

GEMINI_MODEL = "gemini-3.5-flash-lite"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
BUFFER_API_KEY = os.getenv("BUFFER_API_KEY")
BUFFER_CHANNEL_ID = os.getenv("BUFFER_CHANNEL_ID")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

DATA_DIR = "data"

LATEST_NEWS_FILE = os.path.join(DATA_DIR, "latest_news.json")
NEWS_ANALYSIS_FILE = os.path.join(DATA_DIR, "news_analysis.json")
CONTENT_QUEUE_FILE = os.path.join(DATA_DIR, "content_queue.json")

ANALYZE_PROMPT_FILE = "prompt/analyze_devblog_sections.txt"
X_POST_PROMPT_FILE = "prompt/generate_x_post.txt"
GENERAL_ANNOUNCEMENT_PROMPT_FILE = "prompt/generate_general_announcement.txt"


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

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    ensure_data_dir()

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_prompt(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def parse_json_response(text):
    """
    Gemini puede devolver JSON directamente o envolverlo
    en bloques ```json.
    """

    if isinstance(text, dict):
        return text

    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")

        if start != -1 and end != -1 and end > start:
            return json.loads(cleaned[start:end + 1])

        raise


def get_gemini_client():
    if not GEMINI_API_KEY:
        raise RuntimeError("Falta GEMINI_API_KEY.")

    return genai.Client(api_key=GEMINI_API_KEY)


# ============================================================
# SCRAPER
# ============================================================

def get_latest_news():
    response = requests.get(
        NEWS_URL,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    for link in soup.select('a[href*="/news/"]'):
        href = link.get("href")

        if not href:
            continue

        if href == "/news/":
            continue

        if not href.startswith("/news/"):
            continue

        return urljoin(BASE_URL, href)

    raise RuntimeError("No se encontró ninguna noticia en Facepunch.")


def extract_article_metadata(soup):
    title = None
    date = None
    article_type = None

    # --------------------------------------------------------
    # TITLE
    # --------------------------------------------------------

    og_title = soup.find("meta", property="og:title")

    if og_title and og_title.get("content"):
        title = og_title["content"].strip()

    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)

    if title:
        title = re.sub(r"\s*-\s*News\s*-\s*Rust\s*$", "", title).strip()

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    date_patterns = [
        r"\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b",
        r"\b\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\b",
        r"\b[A-Za-z]+\s+\d{1,2},\s+\d{4}\b"
    ]

    page_text = soup.get_text(" ", strip=True)

    for pattern in date_patterns:
        match = re.search(pattern, page_text)

        if match:
            date = match.group(0)
            break

    # --------------------------------------------------------
    # TYPE
    # --------------------------------------------------------

    if soup.select('a[href*="/news/"]'):
        article_type = "DEVBLOG"

    return {
        "title": title or "Rust Update",
        "date": date or "",
        "type": article_type or "DEVBLOG"
    }


def scrape_article(url):
    response = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    metadata = extract_article_metadata(soup)

    sections = []

    for block in soup.select(".news-section-block"):

        header = block.select_one(".section-header")

        if not header:
            continue

        title_element = header.select_one(".title")
        author_element = header.select_one(".author")

        title = (
            title_element.get_text(" ", strip=True)
            if title_element
            else ""
        )

        author = (
            author_element.get_text(" ", strip=True)
            if author_element
            else ""
        )

        if not title:
            continue

        if title == "⠀":
            continue

        content_element = block.select_one(".content")

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

            image_url = urljoin(url, src)

            if image_url not in images:
                images.append(image_url)

        sections.append({
            "title": title,
            "author": author,
            "content": content,
            "images": images
        })

    return metadata, sections


# ============================================================
# ANALISIS GEMINI
# ============================================================

def analyze_sections(article, sections):
    prompt = load_prompt(ANALYZE_PROMPT_FILE)

    serialized_sections = []

    for index, section in enumerate(sections, start=1):
        serialized_sections.append(
            f"""
SECCIÓN {index}

Título:
{section["title"]}

Autor:
{section["author"]}

Contenido:
{section["content"]}

Imágenes:
{json.dumps(section["images"], ensure_ascii=False)}
""".strip()
        )

    full_prompt = prompt

    full_prompt = full_prompt.replace(
        "{{ARTICLE_TITLE}}",
        article["title"]
    )

    full_prompt = full_prompt.replace(
        "{{ARTICLE_DATE}}",
        article["date"]
    )

    full_prompt = full_prompt.replace(
        "{{ARTICLE_TYPE}}",
        article["type"]
    )

    full_prompt = full_prompt.replace(
        "{{SECTIONS}}",
        "\n\n".join(serialized_sections)
    )

    client = get_gemini_client()

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=full_prompt
    )

    result = parse_json_response(response.text)

    if not isinstance(result, list):
        raise RuntimeError(
            "Gemini no devolvió una lista de análisis."
        )

    return result


# ============================================================
# COLA
# ============================================================

def build_content_queue(article, sections, analysis):
    analysis_by_title = {
        item.get("title", "").strip(): item
        for item in analysis
        if isinstance(item, dict)
    }

    minimum_score = 75

    items = []

    for section in sections:

        title = section["title"]

        result = analysis_by_title.get(title)

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

        if score < minimum_score:
            continue

        items.append({
            "article_url": article["url"],
            "article_title": article["title"],
            "article_date": article["date"],
            "article_type": article["type"],

            "title": title,
            "author": section["author"],
            "content": section["content"],
            "images": section["images"],

            "importance": result.get("importance", 0),
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
        })

    items.sort(
        key=lambda x: (
            x["publication_score"],
            x["importance"],
            x["interaction_potential"],
            x["social_value"]
        ),
        reverse=True
    )

    for index, item in enumerate(items, start=1):
        item["priority"] = index

    queue = {
        "article": article,

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
            "total_sections": len(sections),
            "selected_sections": len(items)
        },

        "items": items
    }

    return queue


# ============================================================
# POSTS ANTERIORES
# ============================================================

def get_last_posts(queue):
    posts = []

    for item in queue.get("items", []):
        generated_text = item.get("generated_text")

        if generated_text:
            posts.append(generated_text)

    return posts[-10:]


# ============================================================
# ANUNCIO GENERAL
# ============================================================

def generate_general_announcement(queue):
    prompt = load_prompt(
        GENERAL_ANNOUNCEMENT_PROMPT_FILE
    )

    article = queue["article"]

    sections = []

    for item in queue.get("items", []):
        sections.append(
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
        "{{LAST_POSTS}}",
        "\n\n".join(get_last_posts(queue))
    )

    prompt = prompt.replace(
        "{{SECTIONS}}",
        "\n\n".join(sections)
    )

    client = get_gemini_client()

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )

    result = parse_json_response(response.text)

    x_text = result.get("x_text")
    discord_text = result.get("discord_text")

    if not x_text:
        raise RuntimeError(
            "El anuncio general no contiene x_text."
        )

    if not discord_text:
        raise RuntimeError(
            "El anuncio general no contiene discord_text."
        )

    return {
        "x_text": x_text.strip(),
        "discord_text": discord_text.strip()
    }


# ============================================================
# GENERAR POST DE SECCIÓN
# ============================================================

def generate_x_post(item, queue):
    prompt = load_prompt(X_POST_PROMPT_FILE)

    prompt = prompt.replace(
        "{{ARTICLE_TITLE}}",
        item["article_title"]
    )

    prompt = prompt.replace(
        "{{ARTICLE_DATE}}",
        item["article_date"]
    )

    prompt = prompt.replace(
        "{{ARTICLE_TYPE}}",
        item["article_type"]
    )

    prompt = prompt.replace(
        "{{SECTION_TITLE}}",
        item["title"]
    )

    prompt = prompt.replace(
        "{{SECTION_CONTENT}}",
        item["content"]
    )

    prompt = prompt.replace(
        "{{LAST_POSTS}}",
        "\n".join(get_last_posts(queue))
    )

    client = get_gemini_client()

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )

    result = parse_json_response(response.text)

    if isinstance(result, dict):
        text = (
            result.get("text")
            or result.get("x_text")
        )
    else:
        text = result

    if not text:
        raise RuntimeError(
            "Gemini no devolvió el texto del post."
        )

    return str(text).strip()


# ============================================================
# BUFFER
# ============================================================

def buffer_create_post(text, image_url=None):
    if not BUFFER_API_KEY:
        raise RuntimeError("Falta BUFFER_API_KEY.")

    if not BUFFER_CHANNEL_ID:
        raise RuntimeError("Falta BUFFER_CHANNEL_ID.")

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
        "channelId": BUFFER_CHANNEL_ID,
        "text": text
    }

    if image_url:
        input_data["assets"] = [
            {
                "image": {
                    "url": image_url
                }
            }
        ]
    else:
        input_data["assets"] = []

    response = requests.post(
        "https://api.buffer.com",
        headers={
            "Authorization": f"Bearer {BUFFER_API_KEY}",
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

    result = response.json()

    if result.get("errors"):
        raise RuntimeError(
            f"Buffer GraphQL error: {json.dumps(result['errors'], ensure_ascii=False)}"
        )

    create_post = (
        result
        .get("data", {})
        .get("createPost")
    )

    if not create_post:
        raise RuntimeError(
            "Buffer no devolvió createPost."
        )

    if create_post.get("message"):
        raise RuntimeError(
            f"Buffer rechazó el post: {create_post.get('message')}"
        )

    post = create_post.get("post")

    if not post:
        raise RuntimeError(
            "Buffer no devolvió el objeto post."
        )

    if not post.get("id"):
        raise RuntimeError(
            "Buffer no devolvió un post ID."
        )

    return post


# ============================================================
# DISCORD
# ============================================================

def publish_discord(text):
    if not DISCORD_WEBHOOK_URL:
        raise RuntimeError(
            "Falta DISCORD_WEBHOOK_URL."
        )

    response = requests.post(
        DISCORD_WEBHOOK_URL,
        json={
            "content": text
        },
        timeout=30
    )

    if response.status_code >= 300:
        raise RuntimeError(
            f"Discord rechazó el mensaje "
            f"({response.status_code}): {response.text}"
        )

    return True


# ============================================================
# ANUNCIO GENERAL
# ============================================================

def process_general_announcement(queue):
    publication = queue["general_publication"]

    # --------------------------------------------------------
    # GENERAR UNA SOLA VEZ
    # --------------------------------------------------------

    if not publication.get("generated"):
        print("Generando anuncio general...")

        generated = generate_general_announcement(queue)

        publication["x_text"] = generated["x_text"]
        publication["discord_text"] = generated["discord_text"]
        publication["generated"] = True
        publication["generated_at"] = now_iso()

        save_json(
            CONTENT_QUEUE_FILE,
            queue
        )

        print("")
        print("========================================")
        print("ANUNCIO GENERAL - X")
        print("========================================")
        print(publication["x_text"])

        print("")
        print("========================================")
        print("ANUNCIO GENERAL - DISCORD")
        print("========================================")
        print(publication["discord_text"])
        print("")

    # --------------------------------------------------------
    # X
    # --------------------------------------------------------

    if not publication.get("x_posted"):
        print("Publicando anuncio general en X mediante Buffer...")

        post = buffer_create_post(
            publication["x_text"]
        )

        publication["x_posted"] = True
        publication["x_posted_at"] = now_iso()
        publication["x_post_id"] = post["id"]

        save_json(
            CONTENT_QUEUE_FILE,
            queue
        )

        print(
            f"Anuncio general publicado en X. "
            f"ID: {post['id']}"
        )

    else:
        print("Anuncio general de X ya publicado.")

    # --------------------------------------------------------
    # DISCORD
    # --------------------------------------------------------

    if not publication.get("discord_posted"):
        print("Publicando anuncio general en Discord...")

        publish_discord(
            publication["discord_text"]
        )

        publication["discord_posted"] = True
        publication["discord_posted_at"] = now_iso()

        save_json(
            CONTENT_QUEUE_FILE,
            queue
        )

        print("Anuncio general publicado en Discord.")

    else:
        print("Anuncio general de Discord ya publicado.")

    # --------------------------------------------------------
    # RESULTADO
    # --------------------------------------------------------

    return (
        publication.get("x_posted")
        and publication.get("discord_posted")
    )


# ============================================================
# SIGUIENTE CONTENIDO
# ============================================================

def get_next_content(queue):
    unpublished = [
        item
        for item in queue.get("items", [])
        if not item.get("published")
    ]

    if not unpublished:
        return None

    unpublished.sort(
        key=lambda x: x.get("priority", 999999)
    )

    return unpublished[0]


def publish_next_content(queue):
    item = get_next_content(queue)

    if not item:
        print("No quedan contenidos pendientes.")
        return False

    print("")
    print("Próximo contenido:")
    print(f"Título: {item['title']}")
    print(f"Score: {item['publication_score']}")
    print(f"Prioridad: {item['priority']}")
    print("")

    print(
        f"Generando post X para: {item['title']}"
    )

    text = generate_x_post(
        item,
        queue
    )

    print("")
    print("Post generado:")
    print(text)
    print("")

    valid_images = [
        image
        for image in item.get("images", [])
        if isinstance(image, str)
        and image.startswith("http")
    ]

    image_url = (
        valid_images[0]
        if valid_images
        else None
    )

    if image_url:
        print(f"Imagen encontrada: {image_url}")
    else:
        print("No se encontró una imagen válida.")

    print("")
    print("Publicando mediante Buffer...")

    post = buffer_create_post(
        text,
        image_url=image_url
    )

    print(
        f"Publicado correctamente en Buffer. "
        f"ID: {post['id']}"
    )

    # --------------------------------------------------------
    # IMPORTANTE:
    # SOLO MARCAMOS COMO PUBLICADO DESPUÉS DE BUFFER
    # --------------------------------------------------------

    item["published"] = True
    item["published_at"] = now_iso()
    item["platform"] = "x"
    item["post_id"] = post["id"]
    item["generated_text"] = text
    item["generated_at"] = now_iso()

    save_json(
        CONTENT_QUEUE_FILE,
        queue
    )

    print("Estado guardado correctamente.")

    return True


# ============================================================
# NUEVO ARTÍCULO
# ============================================================

def is_new_article(article, queue):
    if not queue:
        return True

    current_article = queue.get("article", {})

    return (
        current_article.get("url")
        != article.get("url")
    )


# ============================================================
# MAIN
# ============================================================

def main():
    ensure_data_dir()

    print("========================================")
    print("CALAVERA RUST NEWS")
    print("========================================")
    print("")

    # --------------------------------------------------------
    # 1. SCRAPING
    # --------------------------------------------------------

    print("Buscando última noticia de Rust...")

    latest_url = get_latest_news()

    print(f"Última noticia: {latest_url}")
    print("")

    article_metadata, sections = scrape_article(
        latest_url
    )

    article = {
        "url": latest_url,
        "title": article_metadata["title"],
        "date": article_metadata["date"],
        "type": article_metadata["type"]
    }

    print(f"Título detectado: {article['title']}")
    print(f"Fecha detectada: {article['date']}")
    print(f"Tipo detectado: {article['type']}")
    print(f"Secciones encontradas: {len(sections)}")
    print("")

    # --------------------------------------------------------
    # 2. GUARDAR ÚLTIMA NOTICIA
    # --------------------------------------------------------

    save_json(
        LATEST_NEWS_FILE,
        article
    )

    # --------------------------------------------------------
    # 3. CARGAR COLA
    # --------------------------------------------------------

    queue = load_json(
        CONTENT_QUEUE_FILE,
        None
    )

    new_article = is_new_article(
        article,
        queue
    )

    # --------------------------------------------------------
    # 4. NUEVO PATCH
    # --------------------------------------------------------

    if new_article:

        print("========================================")
        print("NUEVO PATCH DETECTADO")
        print("========================================")
        print("")

        print("Analizando secciones con Gemini...")

        analysis = analyze_sections(
            article,
            sections
        )

        save_json(
            NEWS_ANALYSIS_FILE,
            analysis
        )

        queue = build_content_queue(
            article,
            sections,
            analysis
        )

        save_json(
            CONTENT_QUEUE_FILE,
            queue
        )

        print("")
        print("Cola creada.")
        print(
            f"Secciones seleccionadas: "
            f"{len(queue['items'])}"
        )
        print("")

        # ----------------------------------------------------
        # DÍA 1:
        # SOLO ANUNCIO GENERAL
        # ----------------------------------------------------

        print("Procesando anuncio general...")

        process_general_announcement(
            queue
        )

        print("")
        print("========================================")
        print("DÍA 1 COMPLETADO")
        print("========================================")
        print(
            "No se publica una sección individual "
            "en esta ejecución."
        )

        save_json(
            CONTENT_QUEUE_FILE,
            queue
        )

        return

    # --------------------------------------------------------
    # 5. PATCH YA EXISTENTE
    # --------------------------------------------------------

    print("Patch ya procesado.")
    print("")

    # --------------------------------------------------------
    # 6. ASEGURAR ANUNCIO GENERAL
    # --------------------------------------------------------

    publication = queue.get(
        "general_publication",
        {}
    )

    if not (
        publication.get("x_posted")
        and publication.get("discord_posted")
    ):
        print("El anuncio general todavía no está completo.")

        process_general_announcement(
            queue
        )

        print("")

        # Si el anuncio general se completó en esta ejecución,
        # no consumimos también la primera sección.
        if (
            queue["general_publication"].get("x_posted")
            and queue["general_publication"].get("discord_posted")
        ):
            print("Anuncio general completado.")
            print(
                "La primera sección queda para la próxima ejecución."
            )

            save_json(
                CONTENT_QUEUE_FILE,
                queue
            )

            return

    # --------------------------------------------------------
    # 7. UNA SECCIÓN POR EJECUCIÓN
    # --------------------------------------------------------

    publish_next_content(
        queue
    )

    # --------------------------------------------------------
    # 8. GUARDAR
    # --------------------------------------------------------

    save_json(
        CONTENT_QUEUE_FILE,
        queue
    )

    print("")
    print("========================================")
    print("EJECUCIÓN COMPLETADA")
    print("========================================")


if __name__ == "__main__":
    main()
