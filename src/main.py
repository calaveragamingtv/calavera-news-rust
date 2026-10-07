import json
import os

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

# Puntaje mínimo para que una sección sea considerada
# publicable como contenido individual.
MIN_PUBLICATION_SCORE = 75


def get_page(url):
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


def get_latest_news():
    html = get_page(NEWS_URL)
    soup = BeautifulSoup(html, "html.parser")

    news_links = soup.select("a[href*='/news/']")

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

        return urljoin(BASE_URL, href)

    raise Exception("No se pudo encontrar la última noticia.")


def parse_news(url):
    html = get_page(url)
    soup = BeautifulSoup(html, "html.parser")

    # -----------------------------
    # Article metadata
    # -----------------------------

    title_element = soup.find("h1")
    title = title_element.get_text(" ", strip=True) if title_element else ""

    date_element = soup.find("time")
    date = date_element.get_text(" ", strip=True) if date_element else ""

    news_type = ""

    type_candidates = [
        ".news-type",
        ".type",
        ".news-header .type"
    ]

    for selector in type_candidates:
        element = soup.select_one(selector)

        if element:
            news_type = element.get_text(" ", strip=True)
            break

    # -----------------------------
    # Sections
    # -----------------------------

    sections = []

    section_blocks = soup.select(".news-section-block")

    for block in section_blocks:

        title_element = block.select_one(".section-header .title")

        if not title_element:
            continue

        section_title = title_element.get_text(" ", strip=True)

        # Facepunch puede tener títulos vacíos o caracteres
        # utilizados como separadores.
        if not section_title:
            continue

        if section_title == "⠀":
            continue

        author_element = block.select_one(".section-header .author")
        author = (
            author_element.get_text(" ", strip=True)
            if author_element
            else ""
        )

        content_element = block.select_one(".content")

        content = (
            content_element.get_text("\n", strip=True)
            if content_element
            else ""
        )

        images = []

        if content_element:
            for img in content_element.select("img"):
                src = img.get("src")

                if not src:
                    continue

                images.append(urljoin(BASE_URL, src))

        sections.append({
            "title": section_title,
            "author": author,
            "content": content,
            "images": images
        })

    return {
        "url": url,
        "title": title,
        "date": date,
        "type": news_type,
        "sections": sections
    }


def save_news(news):
    os.makedirs("data", exist_ok=True)

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

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise Exception("No existe GEMINI_API_KEY.")

    client = genai.Client(api_key=api_key)

    sections_text = []

    for index, section in enumerate(news["sections"]):

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
Actuá como editor de contenido especializado en Rust y redes sociales.

Estamos analizando este Devblog oficial de Rust:

Título del artículo:
{news["title"]}

Fecha:
{news["date"]}

Tipo:
{news["type"]}

Tu trabajo NO es resumir todo.

Tu trabajo es decidir qué partes de este Devblog realmente
merecen convertirse en contenido individual para redes sociales.

El objetivo es calidad sobre cantidad.

Pensá como un creador de contenido de Rust que quiere generar:

- interés
- comentarios
- debate
- curiosidad
- utilidad para jugadores
- contenido que valga la pena publicar

NO queremos convertir cada sección del Devblog en un post.

Una sección debe recibir un puntaje alto solamente si realmente
vale la pena gastar una publicación individual en ella.

{''.join(sections_text)}

Respondé ÚNICAMENTE con JSON válido.

El JSON debe ser un array con un objeto por cada sección,
manteniendo exactamente el mismo orden.

Formato obligatorio:

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

1. "title"
Debe ser exactamente el título original de la sección.
NO lo traduzcas.

2. "importance"
Del 1 al 10.

Mide qué tan importante es esta información para jugadores
de Rust y su impacto real en el juego.

3. "interaction_potential"
Del 1 al 10.

Mide cuánto puede generar:
- comentarios
- opiniones
- discusión
- debate
- curiosidad
- reacciones

4. "social_value"
Del 1 al 10.

Mide si realmente vale la pena gastar una publicación
individual en redes sociales.

Pensá como creador de contenido, NO como desarrollador.

5. "publication_score"
Del 1 al 100.

Este es el puntaje MÁS IMPORTANTE.

Respondé a esta pregunta:

"Si solamente pudiera publicar unas pocas cosas interesantes
de este Devblog, ¿qué tan arriba estaría esta sección?"

Tené en cuenta:

- impacto para jugadores
- novedad
- potencial de conversación
- utilidad
- curiosidad
- capacidad de generar contenido
- relevancia para la comunidad Rust
- si merece una publicación individual

No distribuyas los puntajes artificialmente.

Una sección mediocre debe tener un puntaje bajo.

Una sección realmente fuerte debe acercarse a 90-100.

6. "recommended"

Debe ser true solamente cuando realmente consideres que
la sección merece una publicación individual.

Como regla general:

publication_score >= 75 → puede ser recomendada.

Pero utilizá criterio editorial.

7. "publication_type"

Usá solamente:

"standalone"
"related"
"skip"

standalone:
La sección funciona perfectamente como publicación independiente.

related:
Tiene valor, pero está muy relacionada con otra sección
y podría funcionar mejor como contenido complementario.

skip:
No merece una publicación individual.

8. "content_type"

Usá solamente:

"news"
"question"
"debate"
"fact"
"curiosity"

9. "reason"

Explicación corta, natural y en español latino.

NO uses español neutro artificial.

NO escribas texto promocional.

10. Calidad sobre cantidad.

Es preferible recomendar 4 secciones excelentes
antes que 10 secciones mediocres.

11. No recomiendes automáticamente:

- cambios cosméticos menores
- pequeños cambios de UI
- correcciones técnicas poco relevantes
- cambios internos sin impacto para jugadores
- información repetitiva
- contenido que solamente sea interesante para desarrolladores

12. Si varias secciones hablan de la misma característica,
evitá convertirlas automáticamente en publicaciones independientes.

13. Los nombres oficiales de Rust pueden permanecer en inglés.

14. Toda explicación generada debe estar en español latino.

15. No generes tweets todavía.

Solamente analizá y clasificá las secciones.
"""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )

    text = response.text.strip()

    # Limpiar posibles bloques Markdown.
    if text.startswith("```"):
        lines = text.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        text = "\n".join(lines).strip()

    try:
        analyses = json.loads(text)
    except json.JSONDecodeError as error:
        print("Respuesta de Gemini:")
        print(text)
        raise Exception(
            f"Gemini no devolvió JSON válido: {error}"
        )

    if not isinstance(analyses, list):
        raise Exception(
            "Gemini no devolvió un array de análisis."
        )

    if len(analyses) != len(news["sections"]):
        raise Exception(
            "La cantidad de análisis no coincide con la cantidad de secciones."
        )

    return analyses


def save_analysis(news, analyses):
    os.makedirs("data", exist_ok=True)

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


def create_content_queue(news, analyses):

    queue = []

    for section, analysis in zip(
        news["sections"],
        analyses
    ):

        publication_score = analysis.get(
            "publication_score",
            0
        )

        recommended = analysis.get(
            "recommended",
            False
        )

        publication_type = analysis.get(
            "publication_type",
            "skip"
        )

        # -----------------------------
        # Selection rules
        # -----------------------------

        if not recommended:
            continue

        if publication_type == "skip":
            continue

        if publication_score < MIN_PUBLICATION_SCORE:
            continue

        queue_item = {
            "title": section["title"],
            "author": section["author"],
            "content": section["content"],
            "images": section["images"],

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

            "publication_type": publication_type,

            "content_type": analysis.get(
                "content_type",
                "news"
            ),

            "reason": analysis.get(
                "reason",
                ""
            ),

            "published": False
        }

        queue.append(queue_item)

    # -----------------------------
    # Orden editorial
    # -----------------------------
    #
    # No confiamos en el "priority" de Gemini.
    # Python determina el orden de forma determinística.
    #

    queue.sort(
        key=lambda item: (
            item["publication_score"],
            item["interaction_potential"],
            item["importance"]
        ),
        reverse=True
    )

    # -----------------------------
    # Assign priority
    # -----------------------------

    for index, item in enumerate(queue, start=1):
        item["priority"] = index

    data = {
        "article": {
            "url": news["url"],
            "title": news["title"],
            "date": news["date"],
            "type": news["type"]
        },
        "items": queue
    }

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

    print("Buscando última noticia de Rust...")

    latest_url = get_latest_news()

    print(f"Última noticia: {latest_url}")

    print("Parseando noticia...")

    news = parse_news(latest_url)

    print(
        f'Secciones encontradas: {len(news["sections"])}'
    )

    save_news(news)

    print("Analizando secciones con Gemini...")

    analyses = analyze_all_sections(news)

    save_analysis(
        news,
        analyses
    )

    print("Creando content queue...")

    create_content_queue(
        news,
        analyses
    )

    print("Proceso terminado.")


if __name__ == "__main__":
    main()
