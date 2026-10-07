import json
import os
import re

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from google import genai


BASE_URL = "https://rust.facepunch.com"
NEWS_URL = f"{BASE_URL}/news/"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

GEMINI_MODEL = "gemini-3.5-flash-lite"

# Puntaje mínimo para considerar una sección
# como contenido publicable individualmente.
MIN_PUBLICATION_SCORE = 75


def get_page(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    return response.text


def get_latest_news():
    html = get_page(NEWS_URL)

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    news_links = soup.select(
        "a[href*='/news/']"
    )

    for link in news_links:

        href = link.get("href")

        if not href:
            continue

        href = href.strip()

        if href == "/news/":
            continue

        if not href.startswith("/news/"):
            continue

        if href.count("/") < 2:
            continue

        return urljoin(
            BASE_URL,
            href
        )

    raise Exception(
        "No se pudo encontrar la última noticia."
    )


def parse_news(url):

    html = get_page(url)
    soup = BeautifulSoup(html, "html.parser")

    print("DEBUG metadata:")

    print(
        "HTML title:",
        soup.title.get_text(" ", strip=True)
        if soup.title
        else "NO ENCONTRADO"
    )

    print(
        "h1:",
        soup.find("h1").get_text(" ", strip=True)
        if soup.find("h1")
        else "NO ENCONTRADO"
    )

    print(
        "time:",
        soup.find("time").get_text(" ", strip=True)
        if soup.find("time")
        else "NO ENCONTRADO"
    )

    print(
        "DEVBLOG links:",
        len(
            [
                a
                for a in soup.find_all("a")
                if a.get_text(" ", strip=True).upper() == "DEVBLOG"
            ]
        )
    )

    # ---------------------------------------------------------
    # TITLE
    # ---------------------------------------------------------

    title = ""

    if soup.title:
        title = soup.title.get_text(" ", strip=True)

    if not title:
        og_title = soup.select_one('meta[property="og:title"]')

        if og_title:
            title = og_title.get("content", "").strip()

    if not title:
        h1 = soup.find("h1")

        if h1:
            title = h1.get_text(" ", strip=True)

    # ---------------------------------------------------------
    # DATE
    # ---------------------------------------------------------

    date = ""

    # 1. Buscar en <time>
    time_element = soup.find("time")

    if time_element:

        date = (
            time_element.get("datetime")
            or time_element.get_text(" ", strip=True)
        )

    # 2. Buscar metadata estándar
    if not date:

        date_selectors = [
            'meta[property="article:published_time"]',
            'meta[property="article:modified_time"]',
            'meta[name="date"]',
            'meta[name="pubdate"]',
            'meta[name="publishdate"]',
            'meta[itemprop="datePublished"]',
            'meta[itemprop="dateCreated"]'
        ]

        for selector in date_selectors:

            element = soup.select_one(selector)

            if element:

                value = (
                    element.get("content")
                    or element.get("datetime")
                    or ""
                ).strip()

                if value:
                    date = value
                    break

    # 3. Buscar fecha dentro del texto visible
    if not date:

        page_text = soup.get_text(" ", strip=True)

        date_patterns = [
            r"\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b",
            r"\b\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\b",
            r"\b[A-Za-z]+\s+\d{1,2},\s+\d{4}\b"
        ]

        for pattern in date_patterns:

            match = re.search(
                pattern,
                page_text,
                re.IGNORECASE
            )

            if match:
                date = match.group(0)
                break

    # 4. Buscar directamente en el HTML
    if not date:

        date_patterns = [
            r"\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b",
            r"\b\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\b",
            r"\b[A-Za-z]+\s+\d{1,2},\s+\d{4}\b"
        ]

        for pattern in date_patterns:

            match = re.search(
                pattern,
                html,
                re.IGNORECASE
            )

            if match:
                date = match.group(0)
                break

    # ---------------------------------------------------------
    # TYPE
    # ---------------------------------------------------------

    news_type = ""

    for element in soup.find_all("a"):

        text = element.get_text(" ", strip=True)

        if text.upper() == "DEVBLOG":

            news_type = "DEVBLOG"
            break

    if not news_type:

        page_text = soup.get_text(" ", strip=True)

        if "DEVBLOG" in page_text.upper():
            news_type = "DEVBLOG"

    # ---------------------------------------------------------
    # SECTIONS
    # ---------------------------------------------------------

    sections = []

    section_blocks = soup.select(".news-section-block")

    for block in section_blocks:

        title_element = block.select_one(
            ".section-header .title"
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

        author_element = block.select_one(
            ".section-header .author"
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

        content = ""

        if content_element:

            content = content_element.get_text(
                "\n",
                strip=True
            )

        images = []

        if content_element:

            for img in content_element.select("img"):

                src = img.get("src")

                if src:

                    images.append(
                        urljoin(BASE_URL, src)
                    )

        sections.append({
            "title": section_title,
            "author": author,
            "content": content,
            "images": images
        })

    print("Secciones encontradas:", len(sections))
    print("Título detectado:", title)
    print("Fecha detectada:", date)
    print("Tipo detectado:", news_type)

    return {
        "url": url,
        "title": title,
        "date": date,
        "type": news_type,
        "sections": sections
    }

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
            ensure_ascii=False,
            indent=2
        )


def analyze_all_sections(news):

    api_key = os.environ.get(
        "GEMINI_API_KEY"
    )

    if not api_key:

        raise Exception(
            "No existe GEMINI_API_KEY."
        )

    client = genai.Client(
        api_key=api_key
    )

    sections_text = []

    for index, section in enumerate(
        news["sections"]
    ):

        sections_text.append(
            f"""
SECCIÓN {index + 1}

Título:
{section["title"]}

Autor:
{section["author"]}

Contenido:
{section["content"]}
"""
        )

    prompt = f"""
Actuá como editor de contenido especializado
en Rust y redes sociales.

Estamos analizando este Devblog oficial de Rust:

Título:
{news["title"]}

Fecha:
{news["date"]}

Tipo:
{news["type"]}

Tu trabajo NO es resumir todo el Devblog.

Tu trabajo es decidir qué partes realmente merecen
convertirse en contenido individual para redes sociales.

Pensá como un creador de contenido de Rust.

El objetivo es:

- interés
- comentarios
- debate
- curiosidad
- utilidad
- relevancia para jugadores
- contenido que valga la pena publicar

Calidad sobre cantidad.

No queremos convertir cada sección del Devblog
en un post.

{''.join(sections_text)}

Respondé ÚNICAMENTE con JSON válido.

El JSON debe ser un array con un objeto por cada sección,
manteniendo exactamente el mismo orden.

Formato:

[
  {{
    "title": "título original exacto",
    "importance": 0,
    "interaction_potential": 0,
    "social_value": 0,
    "publication_score": 0,
    "recommended": true,
    "publication_type": "standalone",
    "content_type": "news",
    "reason": "explicación breve en español latino"
  }}
]

REGLAS:

1. title

Debe ser exactamente el título original.
No lo traduzcas.

2. importance

Del 1 al 10.

Importancia real para jugadores de Rust.

3. interaction_potential

Del 1 al 10.

Potencial para generar:

- comentarios
- opiniones
- debate
- curiosidad
- reacciones

4. social_value

Del 1 al 10.

Qué tan justificable es gastar una publicación
individual en esta sección.

Pensá como creador de contenido,
no como desarrollador.

5. publication_score

Del 1 al 100.

Es el indicador principal.

Respondé:

"Si solamente pudiera publicar unas pocas cosas
de este Devblog, ¿qué tan arriba estaría esta sección?"

Considerá:

- impacto
- novedad
- utilidad
- curiosidad
- conversación
- relevancia
- potencial de contenido

No distribuyas los números artificialmente.

Una sección mediocre debe tener un score bajo.

Una sección excepcional puede acercarse a 100.

6. recommended

Indica la opinión editorial del modelo.

Debe ser true únicamente si realmente
merece consideración para publicación individual.

IMPORTANTE:

Python utilizará publication_score como filtro final.

No manipules publication_score solamente
para hacer que recommended sea true.

7. publication_type

Usá solamente:

"standalone"
"related"
"skip"

standalone:
Funciona como publicación independiente.

related:
Tiene valor pero está fuertemente relacionada
con otra sección y debería utilizarse como
contenido complementario.

skip:
No merece publicación individual.

8. content_type

Usá solamente:

"news"
"question"
"debate"
"fact"
"curiosity"

9. reason

Explicación breve y natural en español latino.

No escribas texto promocional.

10. Calidad sobre cantidad.

Es preferible recomendar pocas secciones
realmente buenas.

11. Evitá recomendar:

- cambios cosméticos menores
- pequeños cambios de UI
- cambios internos
- optimizaciones técnicas irrelevantes
- información repetitiva
- contenido sin impacto para jugadores

12. Si varias secciones hablan de la misma
característica, considerá si deberían agruparse.

13. Los nombres oficiales de Rust pueden
permanecer en inglés.

14. Toda explicación generada debe estar
en español latino.

15. No generes tweets.

Solamente analizá y clasificá.
"""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )

    text = response.text.strip()

    # ------------------------------------------
    # Clean Markdown JSON fences
    # ------------------------------------------

    if text.startswith("```"):

        lines = text.splitlines()

        if lines and lines[0].startswith(
            "```"
        ):

            lines = lines[1:]

        if lines and lines[-1].strip() == "```":

            lines = lines[:-1]

        text = "\n".join(
            lines
        ).strip()

    # ------------------------------------------
    # Parse JSON
    # ------------------------------------------

    try:

        analyses = json.loads(
            text
        )

    except json.JSONDecodeError as error:

        print(
            "Respuesta de Gemini:"
        )

        print(text)

        raise Exception(
            f"Gemini no devolvió JSON válido: {error}"
        )

    if not isinstance(
        analyses,
        list
    ):

        raise Exception(
            "Gemini no devolvió un array de análisis."
        )

    if len(analyses) != len(
        news["sections"]
    ):

        raise Exception(
            "La cantidad de análisis no coincide "
            "con la cantidad de secciones."
        )

    return analyses


def save_analysis(
    news,
    analyses
):

    os.makedirs(
        "data",
        exist_ok=True
    )

    data = {
        "url": news["url"],
        "title": news["title"],
        "date": news["date"],
        "type": news["type"],
        "analyses": analyses
    }

    with open(
        "data/news_analysis.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )


def create_content_queue(
    news,
    analyses
):

    queue = []

    for section, analysis in zip(
        news["sections"],
        analyses
    ):

        publication_score = analysis.get(
            "publication_score",
            0
        )

        publication_type = analysis.get(
            "publication_type",
            "skip"
        )

        # ======================================
        # FINAL SELECTION RULES
        # ======================================
        #
        # standalone:
        #   puede ser publicación individual.
        #
        # related:
        #   se conserva en el análisis pero NO
        #   entra como publicación individual.
        #
        # skip:
        #   se descarta.
        #

        if publication_type in (
            "skip",
            "related"
        ):

            continue

        if publication_score < (
            MIN_PUBLICATION_SCORE
        ):

            continue

        queue_item = {

            # ----------------------------------
            # Article context
            # ----------------------------------

            "article_url": news["url"],

            "article_title": news["title"],

            "article_date": news["date"],

            "article_type": news["type"],

            # ----------------------------------
            # Section
            # ----------------------------------

            "title": section["title"],

            "author": section["author"],

            "content": section["content"],

            "images": section["images"],

            # ----------------------------------
            # AI analysis
            # ----------------------------------

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

            # ----------------------------------
            # Publication state
            # ----------------------------------

            "published": False,

            "published_at": None,

            "platform": None
        }

        queue.append(
            queue_item
        )

    # ==========================================
    # SORT
    # ==========================================

    queue.sort(
        key=lambda item: (
            item["publication_score"],
            item["interaction_potential"],
            item["importance"]
        ),
        reverse=True
    )

    # ==========================================
    # PRIORITY
    # ==========================================

    for index, item in enumerate(
        queue,
        start=1
    ):

        item["priority"] = index

    # ==========================================
    # FINAL QUEUE OBJECT
    # ==========================================

    data = {

        "article": {
            "url": news["url"],
            "title": news["title"],
            "date": news["date"],
            "type": news["type"]
        },

        "selection": {

            "minimum_publication_score":
                MIN_PUBLICATION_SCORE,

            "total_sections":
                len(news["sections"]),

            "selected_sections":
                len(queue)
        },

        "items": queue
    }

    # ==========================================
    # SAVE
    # ==========================================

    with open(
        "data/content_queue.json",
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2
        )

    # ==========================================
    # LOG
    # ==========================================

    print(
        f"Contenido seleccionado: {len(queue)}"
    )

    for item in queue:

        print(
            f'{item["priority"]}. '
            f'{item["title"]} '
            f'({item["publication_score"]})'
        )


def main():

    print(
        "Buscando última noticia de Rust..."
    )

    latest_url = get_latest_news()

    print(
        f"Última noticia: {latest_url}"
    )

    print(
        "Parseando noticia..."
    )

    news = parse_news(
        latest_url
    )

    print(
        f'Secciones encontradas: '
        f'{len(news["sections"])}'
    )

    print(
        f'Título detectado: '
        f'{news["title"]}'
    )

    print(
        f'Fecha detectada: '
        f'{news["date"]}'
    )

    print(
        f'Tipo detectado: '
        f'{news["type"]}'
    )

    save_news(
        news
    )

    print(
        "Analizando secciones con Gemini..."
    )

    analyses = analyze_all_sections(
        news
    )

    save_analysis(
        news,
        analyses
    )

    print(
        "Creando content queue..."
    )

    create_content_queue(
        news,
        analyses
    )

    print(
        "Proceso terminado."
    )


if __name__ == "__main__":
    main()
