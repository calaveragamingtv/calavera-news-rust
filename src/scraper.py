import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://rust.facepunch.com"
NEWS_URL = f"{BASE_URL}/news/"


# ============================================================
def get_latest_news():
    """Devuelve la URL del artículo más reciente, nunca la página /news/."""
    print("Consultando noticias de Rust...")
    response = requests.get(NEWS_URL, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    candidates = []
    seen = set()

    # Los enlaces de las tarjetas/noticias suelen apuntar a /news/<slug>/.
    for link in soup.select('a[href]'):
        href = (link.get("href") or "").strip()
        if not href:
            continue
        absolute = urljoin(BASE_URL, href)
        parsed = urlparse(absolute)
        path = parsed.path.rstrip("/")

        if parsed.netloc.lower() not in {"rust.facepunch.com", "www.rust.facepunch.com"}:
            continue
        if not path.startswith("/news/") or path == "/news":
            continue
        if absolute in seen:
            continue
        seen.add(absolute)

        # Priorizar enlaces que tengan título o estén dentro de un bloque de noticia.
        text = link.get_text(" ", strip=True)
        parent_classes = " ".join(link.parent.get("class", [])) if link.parent else ""
        score = 0
        if text:
            score += 1
        if any(token in parent_classes.lower() for token in ("news", "article", "card", "post")):
            score += 2
        if link.select_one("img, picture"):
            score += 1
        candidates.append((score, absolute))

    if not candidates:
        raise RuntimeError("No se encontró un enlace a un artículo individual en la página de noticias")

    # Mantener el orden del HTML (Facepunch muestra primero la noticia más reciente).
    best_score = max(score for score, _ in candidates)
    url = next(url for score, url in candidates if score == best_score)
    print(f"Última noticia detectada: {url}")
    return url


def scrape_article(url):
    print(f"Scrapeando artículo: {url}")

    response = requests.get(url, timeout=30)
    response.raise_for_status()

    html = response.text
    soup = BeautifulSoup(html, "html.parser")

    # --------------------------------------------------------
    # METADATA
    # --------------------------------------------------------

    html_title = (
        soup.title.get_text(" ", strip=True)
        if soup.title
        else ""
    )

    article_title = html_title

    suffix = " - News - Rust"
    if article_title.endswith(suffix):
        article_title = article_title[:-len(suffix)].strip()

    date_patterns = [
        r"\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b",
        r"\b\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\b",
        r"\b[A-Za-z]+\s+\d{1,2},\s+\d{4}\b"
    ]

    article_date = None

    for pattern in date_patterns:
        match = re.search(pattern, html)
        if match:
            article_date = match.group(0)
            break

    article_type = "DEVBLOG"

    # --------------------------------------------------------
    # EXTRACCION DE IMAGENES Y VIDEOS
    # --------------------------------------------------------

    video_extensions = (
        ".mp4",
        ".webm",
        ".mov",
        ".m4v",
        ".ogv",
        ".avi"
    )

    def extract_media(container):
        images = []
        videos = []

        # Imágenes
        for img in container.select("img"):
            src = (
                img.get("src")
                or img.get("data-src")
                or img.get("data-original")
            )

            if not src:
                continue

            image_url = urljoin(url, src)

            if image_url not in images:
                images.append(image_url)

        # Videos embebidos
        for video in container.select("video"):
            sources = []

            if video.get("src"):
                sources.append(video.get("src"))

            for source in video.select("source"):
                src = source.get("src")
                if src:
                    sources.append(src)

            for src in sources:
                video_url = urljoin(url, src)

                if video_url not in videos:
                    videos.append(video_url)

        # Enlaces directos a archivos de video
        for link in container.select("a[href]"):
            href = link.get("href", "").strip()
            path = urlparse(href).path.lower()

            if path.endswith(video_extensions):
                video_url = urljoin(url, href)

                if video_url not in videos:
                    videos.append(video_url)

        return images, videos

    # --------------------------------------------------------
    # MEDIOS DE PORTADA (HERO), FUERA DE LAS SECCIONES
    # --------------------------------------------------------

    video_extensions = (".mp4", ".webm", ".mov", ".m4v", ".ogv", ".avi")

    def extract_page_videos(page_soup):
        found = []
        for video in page_soup.select("video"):
            sources = []
            for attr in ("src", "data-src", "data-video-src"):
                if video.get(attr):
                    sources.append(video.get(attr))
            for source in video.select("source"):
                for attr in ("src", "data-src"):
                    if source.get(attr):
                        sources.append(source.get(attr))
            for raw in sources:
                candidate = urljoin(url, raw.strip())
                if urlparse(candidate).path.lower().endswith(video_extensions) and candidate not in found:
                    found.append(candidate)

        # Algunos heroes enlazan directamente el MP4 sin usar una etiqueta <video>.
        for element in page_soup.select("a[href], source[src], [data-video-src], [data-src]"):
            raw = element.get("href") or element.get("src") or element.get("data-video-src") or element.get("data-src")
            if not raw:
                continue
            candidate = urljoin(url, raw.strip())
            if urlparse(candidate).path.lower().endswith(video_extensions) and candidate not in found:
                found.append(candidate)
        return found

    # Primer video de la página = video de portada/hero (por ejemplo, darkness_falls-blog-bg.mp4).
    page_videos = extract_page_videos(soup)
    cover_video = page_videos[0] if page_videos else None

    # --------------------------------------------------------
    # SECCIONES
    # --------------------------------------------------------

    sections = []

    blocks = soup.select(".news-section-block")

    for block in blocks:
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

        if not title or title.strip() == "⠀":
            continue

        content_element = block.select_one(".content")

        if not content_element:
            continue

        content = content_element.get_text("\n", strip=True)

        images, videos = extract_media(content_element)

        sections.append({
            "title": title,
            "author": author,
            "content": content,
            "images": images,
            "videos": videos
        })

    # --------------------------------------------------------
    # IMAGENES Y VIDEOS GENERALES DEL PATCH
    # --------------------------------------------------------

    article_images = []
    article_videos = []

    # El video de portada debe quedar primero para que el anuncio general lo use.
    if cover_video:
        article_videos.append(cover_video)

    for video_url in page_videos:
        if video_url not in article_videos:
            article_videos.append(video_url)

    for section in sections:
        for image_url in section.get("images", []):
            if image_url not in article_images:
                article_images.append(image_url)

        for video_url in section.get("videos", []):
            if video_url not in article_videos:
                article_videos.append(video_url)

    print()
    print("DEBUG metadata:")
    print(f"HTML title: {html_title}")
    print("h1: NO ENCONTRADO")
    print(f"Fecha detectada: {article_date}")
    print(f"Tipo detectado: {article_type}")
    print(f"Secciones encontradas: {len(sections)}")
    print(f"Título detectado: {article_title}")
    print(f"Imágenes generales encontradas: {len(article_images)}")
    print(f"Videos generales encontrados: {len(article_videos)}")

    for section in sections:
        print(
            f"Sección '{section['title']}': "
            f"{len(section['images'])} imágenes, "
            f"{len(section['videos'])} videos"
        )

    return {
        "url": url,
        "title": article_title,
        "date": article_date,
        "type": article_type,
        "sections": sections,
        "images": article_images,
        "videos": article_videos,
        "cover_video": cover_video
    }


