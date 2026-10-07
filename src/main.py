import json
import os
import time

import requests

from bs4 import BeautifulSoup
from urllib.parse import urljoin
from google import genai


BASE_URL = "https://rust.facepunch.com"
NEWS_URL = f"{BASE_URL}/news/"

HEADERS = {
    "User-Agent": "RustNewsBot/1.0"
}


# ============================================================
# WEB
# ============================================================

def get_page(url):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    return BeautifulSoup(
        response.text,
        "html.parser"
    )


def get_latest_news():

    soup = get_page(NEWS_URL)

    links = []

    for link in soup.find_all("a", href=True):

        href = link["href"]

        if "/news/" in href and href != "/news/":

            full_url = urljoin(
                BASE_URL,
                href
            )

            if full_url not in links:

                links.append(full_url)

    if not links:

        raise RuntimeError(
            "No se encontraron noticias en Facepunch."
        )

    return links[0]


# ============================================================
# PARSER DE NOTICIA
# ============================================================

def parse_news(url):

    soup = get_page(url)

    result = {
        "url": url,
        "title": None,
        "date": None,
        "type": None,
        "sections": []
    }

    # ----------------------------
    # Título
    # ----------------------------

    if soup.title:

        result["title"] = soup.title.get_text(
            " ",
            strip=True
        )

    # ----------------------------
    # Fecha / tipo
    # ----------------------------

    tags = soup.select_one(".tags")

    if tags:

        tag_text = tags.get_text(
            " ",
            strip=True
        )

        parts = tag_text.split()

        if parts:

            result["date"] = " ".join(
                parts[:3]
            )

        if "DEVBLOG" in tag_text:

            result["type"] = "DEVBLOG"

    # ----------------------------
    # Secciones
    # ----------------------------

    sections = soup.select(
        ".news-section-block"
    )

    for section in sections:

        title_element = section.select_one(
            ".section-header .title"
        )

        if not title_element:
            continue

        title = title_element.get_text(
            " ",
            strip=True
        )

        # Ignorar bloques que no son secciones reales
        if not title or title == "⠀":
            continue

        # ------------------------
        # Autor
        # ------------------------

        author_element = section.select_one(
            ".section-header .author"
        )

        author = (

            author_element.get_text(
                " ",
                strip=True
            )

            if author_element

            else None
        )

        # ------------------------
        # Contenido
        # ------------------------

        content_element = section.select_one(
            ".content"
        )

        content = (

            content_element.get_text(
                " ",
                strip=True
            )

            if content_element

            else ""
        )

        # ------------------------
        # Imágenes
        # ------------------------

        images = []

        for image in section.select(
            ".content img"
        ):

            src = image.get("src")

            if src:

                images.append(
                    urljoin(
                        url,
                        src
                    )
                )

        # ------------------------
        # Guardar sección
        # ------------------------

        result["sections"].append({

            "title": title,

            "author": author,

            "content": content,

            "images": images

        })

    return result


# ============================================================
# GUARDAR NOTICIA
# ============================================================

def save_news(news):

    os.makedirs(
        "data",
        exist_ok=True
    )

    with open(
        "data/latest_news.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            news,
            file,
            indent=2,
            ensure_ascii=False
        )


# ============================================================
# GEMINI
# ============================================================

def analyze_all_sections(news):

    api_key = os.environ.get(
        "GEMINI_API_KEY"
    )

    if not api_key:

        raise RuntimeError(
            "No se encontró GEMINI_API_KEY."
        )

    client = genai.Client(
        api_key=api_key
    )

    # --------------------------------------------------------
    # Preparar todas las secciones para Gemini
    # --------------------------------------------------------

    sections_text = ""

    for index, section in enumerate(
        news["sections"],
        start=1
    ):

        sections_text += f"""
SECTION {index}

Title:
{section["title"]}

Author:
{section["author"]}

Content:
{section["content"]}

--------------------------------
"""

    # --------------------------------------------------------
    # Prompt
    # --------------------------------------------------------

    prompt = f"""
You are a Rust game content analyst.

Analyze ALL sections of this Rust news article.

Your goal is to determine which sections are worth turning into
individual pieces of content for the Rust community on X.

ARTICLE:

Title:
{news["title"]}

Date:
{news["date"]}

Type:
{news["type"]}


SECTIONS:

{sections_text}


RETURN FORMAT:

Return ONLY valid JSON.

Use exactly this structure:

{{
  "sections": [
    {{
      "title": "section title",
      "importance": 0,
      "interaction_potential": 0,
      "recommended": true,
      "content_type": "news",
      "reason": "short explanation"
    }}
  ]
}}


RULES:

- Return EXACTLY one analysis object for every section.
- Keep the original section titles.
- importance must be an integer from 1 to 10.
- interaction_potential must be an integer from 1 to 10.
- recommended must be true or false.
- recommended should be true only when the section deserves
  its own X post.
- Do NOT recommend every section.
- content_type must be one of:
  "news"
  "question"
  "debate"
  "fact"
  "curiosity"
- reason must be short.
- Compare the sections against each other.
- Prioritize:
  - important gameplay changes
  - new mechanics
  - major balance changes
  - controversial changes
  - useful information for players
  - surprising facts
  - topics likely to generate discussion
- Minor technical fixes should normally NOT be recommended.
- Do not invent information.
- Only use information contained in the article sections.
"""

    # --------------------------------------------------------
    # Llamada a Gemini
    # --------------------------------------------------------

    for attempt in range(3):

        try:

            print(
                "\nEnviando todas las secciones "
                "a Gemini..."
            )

            response = client.models.generate_content(

                model="gemini-3.5-flash-lite",

                contents=prompt

            )

            print(
                "\nRespuesta recibida de Gemini."
            )

            # ------------------------------------------------
            # Convertir respuesta a JSON
            # ------------------------------------------------

            try:

                result = json.loads(
                    response.text
                )

            except json.JSONDecodeError:

                print(
                    "\nERROR: Gemini no devolvió "
                    "JSON válido."
                )

                print(
                    "\nRespuesta de Gemini:"
                )

                print(
                    response.text
                )

                raise

            # ------------------------------------------------
            # Validar estructura
            # ------------------------------------------------

            if "sections" not in result:

                raise RuntimeError(
                    "La respuesta de Gemini no contiene "
                    "la propiedad 'sections'."
                )

            return result["sections"]

        except Exception as error:

            print(
                f"\nGemini intento "
                f"{attempt + 1}/3 falló:"
            )

            print(
                error
            )

            if attempt < 2:

                print(
                    "\nEsperando 30 segundos "
                    "antes de reintentar..."
                )

                time.sleep(30)

            else:

                raise


# ============================================================
# GUARDAR ANÁLISIS
# ============================================================

def save_analysis(news, analyses):

    os.makedirs(
        "data",
        exist_ok=True
    )

    result = {

        "url": news["url"],

        "title": news["title"],

        "date": news["date"],

        "type": news["type"],

        "sections": analyses

    }

    with open(
        "data/news_analysis.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            result,
            file,
            indent=2,
            ensure_ascii=False
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "================================"
    )

    print(
        "       RUST NEWS BOT"
    )

    print(
        "================================"
    )

    # --------------------------------------------------------
    # 1. Buscar última noticia
    # --------------------------------------------------------

    print(
        "\nBuscando última noticia..."
    )

    latest_url = get_latest_news()

    print(
        f"URL: {latest_url}"
    )

    # --------------------------------------------------------
    # 2. Parsear noticia
    # --------------------------------------------------------

    print(
        "\nAnalizando noticia..."
    )

    news = parse_news(
        latest_url
    )

    # --------------------------------------------------------
    # 3. Guardar noticia completa
    # --------------------------------------------------------

    save_news(
        news
    )

    print(
        "\nNoticia guardada en "
        "data/latest_news.json"
    )

    print(
        f"\nSe encontraron "
        f"{len(news['sections'])} secciones."
    )

    # --------------------------------------------------------
    # 4. Analizar TODAS las secciones
    #    con UNA sola llamada a Gemini
    # --------------------------------------------------------

    print(
        "\nAnalizando todas las secciones "
        "con Gemini..."
    )

    analyses = analyze_all_sections(
        news
    )

    # --------------------------------------------------------
    # 5. Guardar análisis
    # --------------------------------------------------------

    save_analysis(
        news,
        analyses
    )

    print(
        "\n================================"
    )

    print(
        "      ANALISIS COMPLETADO"
    )

    print(
        "================================"
    )

    print(
        "\nAnálisis guardado en "
        "data/news_analysis.json"
    )

    print(
        f"\nSe analizaron "
        f"{len(analyses)} secciones."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()
