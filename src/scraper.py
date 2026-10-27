import re

import requests

from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


BASE_URL = "https://rust.facepunch.com"
NEWS_URL = f"{BASE_URL}/news/"


# ============================================================
# ULTIMA NOTICIA
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


# ============================================================
# SCRAPEAR ARTICULO
# ============================================================

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

    suffix = " - News - Rust"

    if article_title.endswith(
        suffix
    ):
        article_title = article_title[
            :-len(suffix)
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

        # ----------------------------------------------------
        # IMAGENES
        # ----------------------------------------------------

        for img in container.select(
            "img"
        ):
            src = (
                img.get("src")
                or img.get("data-src")
                or img.get("data-original")
            )

            if not src:
                continue

            image_url = urljoin(
                url,
                src
            )

            if image_url not in images:
                images.append(
                    image_url
                )

        # ----------------------------------------------------
        # VIDEOS EMBEBIDOS
        # ----------------------------------------------------

        for video in container.select(
            "video"
        ):
            sources = []

            if video.get("src"):
                sources.append(
                    video.get("src")
                )

            for source in video.select(
                "source"
            ):
                src = source.get("src")

                if src:
                    sources.append(
                        src
                    )

            for src in sources:
                video_url = urljoin(
                    url,
                    src
                )

                if video_url not in videos:
                    videos.append(
                        video_url
                    )

        # ----------------------------------------------------
        # LINKS DIRECTOS A VIDEOS
        # ----------------------------------------------------

        for link in container.select(
            "a[href]"
        ):
            href = link.get(
                "href",
                ""
            ).strip()

            path = urlparse(
                href
            ).path.lower()

            if path.endswith(
                video_extensions
            ):
                video_url = urljoin(
                    url,
                    href
                )

                if video_url not in videos:
                    videos.append(
                        video_url
                    )

        return images, videos

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

        images, videos = extract_media(
            content_element
        )

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

    for section in sections:

        for image_url in section.get(
            "images",
            []
        ):
            if image_url not in article_images:
                article_images.append(
                    image_url
                )

        for video_url in section.get(
            "videos",
            []
        ):
            if video_url not in article_videos:
                article_videos.append(
                    video_url
                )

    # --------------------------------------------------------
    # DEBUG
    # --------------------------------------------------------

    print()
    print(
        "DEBUG metadata:"
    )

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

    print(
        f"Imágenes generales encontradas: "
        f"{len(article_images)}"
    )

    print(
        f"Videos generales encontrados: "
        f"{len(article_videos)}"
    )

    for section in sections:
        print(
            f"Sección '{section['title']}': "
            f"{len(section['images'])} imágenes, "
            f"{len(section['videos'])} videos"
        )

    # --------------------------------------------------------
    # RESULTADO
    # --------------------------------------------------------

    return {
        "url": url,
        "title": article_title,
        "date": article_date,
        "type": article_type,
        "sections": sections,
        "images": article_images,
        "videos": article_videos
    }
