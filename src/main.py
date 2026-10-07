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

    print("Analizando secciones con Gemini...")

    sections = news["sections"]

    sections_text = []

    for index, section in enumerate(sections, start=1):

        sections_text.append(
            f"""
SECCIÓN {index}

Título:
{section["title"]}

Autor:
{section["author"]}

Contenido:
{section["content"]}
"""
        )

    article_text = "\n".join(sections_text)

    prompt = f"""
Sos un editor de contenido especializado en Rust y en comunidades de jugadores.

Tenés que analizar un Devblog completo de Rust y decidir QUÉ partes realmente
merecen convertirse en contenido independiente para redes sociales.

IMPORTANTE:
No quiero maximizar la cantidad de publicaciones.
Quiero seleccionar solamente los cambios que realmente tienen valor para
los jugadores y para una cuenta de contenido de Rust.

DEVblog:
Título: {news["title"]}
Fecha: {news["date"]}
Tipo: {news["type"]}

SECCIONES:
{article_text}

Para CADA sección devolvé exactamente un objeto JSON con esta estructura:

{{
  "title": "título original exacto de la sección",
  "importance": 0,
  "interaction_potential": 0,
  "social_value": 0,
  "publication_score": 0,
  "recommended": true,
  "publication_type": "standalone",
  "content_type": "news",
  "reason": "explicación breve en español latinoamericano"
}}

REGLAS:

1. title
Debe ser EXACTAMENTE el título original de la sección.
No lo traduzcas.
No lo cambies.
No lo resumas.

2. importance
Del 1 al 10.
¿Qué tan importante es este cambio para los jugadores de Rust?

10 = cambio enorme que afecta fuertemente al gameplay o a la experiencia.
1 = cambio prácticamente irrelevante para un jugador común.

3. interaction_potential
Del 1 al 10.

¿Qué tan probable es que genere:
- comentarios
- debate
- opiniones
- curiosidad
- discusiones entre jugadores
- reacciones

No confundas importancia técnica con capacidad de generar conversación.

4. social_value
Del 1 al 10.

Pensá como un creador de contenido de Rust.

Pregunta:
"¿Vale la pena gastar UNA publicación individual de X en esto?"

No pienses como desarrollador.
Pensá como creador.

5. publication_score
Del 1 al 100.

Este es el criterio MÁS IMPORTANTE.

Respondé:
"Si solamente pudiera publicar unas pocas cosas de este Devblog,
¿qué tan arriba estaría esta sección?"

Una sección puede ser importante pero NO merecer una publicación independiente.

6. recommended

Debe ser true solamente cuando realmente recomendarías convertir esta
sección en contenido.

No pongas true simplemente porque el cambio sea interesante.

7. publication_type

Solo existen tres valores:

"standalone"
"related"
"skip"

Usá "standalone" SOLO si la sección tiene suficiente entidad para ser
un contenido independiente.

MUY IMPORTANTE:

Si una sección forma parte natural de otro cambio más grande del mismo
Devblog, NO debe ser standalone.

Por ejemplo:

Si el Devblog presenta un nuevo sistema "LIVESTOCK" y luego tiene secciones
sobre economía, leche, animales, cercos, etc., esas secciones NO deberían
convertirse automáticamente en publicaciones independientes.

En ese caso:

LIVESTOCK → standalone

Cambios menores relacionados con LIVESTOCK → related

Cambios sin valor suficiente → skip

"related" significa:
"Es interesante, pero sería mejor mencionarlo como parte de otro contenido
y NO gastar una publicación independiente en esto."

"standalone" significa:
"Si publico solamente esto, el contenido sigue teniendo sentido y merece
una publicación propia."

"skip" significa:
"No merece contenido social."

8. content_type

Elegí uno:

"news"
"question"
"debate"
"fact"
"curiosity"

9. reason

Explicá brevemente en español latinoamericano por qué tomaste la decisión.

REGLA EDITORIAL PRINCIPAL:

CALIDAD > CANTIDAD.

Un Devblog NO necesita producir muchos posts.

Es perfectamente válido que de 24 secciones solamente 4, 5 o 6 sean
realmente publicables.

También es válido que una sección con publication_score alto sea "related"
si su información debería formar parte de otro contenido.

NO conviertas automáticamente en standalone:
- pequeños cambios
- cambios técnicos internos
- mejoras visuales menores
- cambios de UI
- cambios de rendimiento que el jugador casi no percibe
- detalles secundarios de una feature principal
- información repetida de otra sección
- partes pequeñas de un sistema más grande

PRIORIZÁ:

- cambios importantes de gameplay
- nuevas mecánicas
- cambios que afectan estrategias
- cambios que pueden generar debate
- cambios que sorprenden a los jugadores
- cambios que modifican cómo se juega Rust
- cambios que generan preguntas o discusión
- novedades suficientemente grandes para funcionar como publicación propia

REGLA SOBRE SECCIONES RELACIONADAS:

Antes de marcar una sección como standalone preguntate:

"¿Podría publicar esto mañana como un post independiente sin repetir
información que ya publiqué sobre otra sección?"

Si la respuesta es NO → related.

Si la respuesta es SÍ → puede ser standalone.

IMPORTANTE:

No generes tweets.
No escribas textos para X.
No escribas titulares nuevos.

Solo analizá y clasificá las secciones.

Todos los campos de texto generados por vos deben estar en español
latinoamericano, EXCEPTO:
- title, que debe conservarse exactamente
- nombres oficiales de Rust
- nombres de items, monumentos, sistemas o mecánicas que oficialmente
  estén en inglés

Devolvé ÚNICAMENTE un JSON válido con este formato:

[
  {{
    "title": "...",
    "importance": 0,
    "interaction_potential": 0,
    "social_value": 0,
    "publication_score": 0,
    "recommended": true,
    "publication_type": "standalone",
    "content_type": "news",
    "reason": "..."
  }}
]

No agregues markdown.
No agregues explicaciones fuera del JSON.
"""

    client = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY")
    )

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json"
        }
    )

    try:

        analyses = json.loads(response.text)

    except json.JSONDecodeError:

        print("ERROR: Gemini no devolvió JSON válido.")
        print(response.text)

        raise

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
