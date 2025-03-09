import logging
import os
from requests import get
from markitdown import MarkItDown

from .guid import guid

logger = logging.getLogger(__name__)

cache_dir = os.path.join("build", "cache")
os.makedirs(name=cache_dir, exist_ok=True)


def get_article_html_file(link: str) -> str:
    htmlfile = os.path.join(cache_dir, guid(link) + ".html")

    if os.path.exists(htmlfile):
        return htmlfile

    logger.info("miss html %s", link)

    response = get(link)
    with open(htmlfile, "w") as file:
        file.write(response.text)

    return htmlfile


def get_article_markdown(link: str) -> str:
    mdfile = os.path.join(cache_dir, guid(link) + ".md")

    if os.path.exists(mdfile):
        with open(mdfile) as file:
            return file.read()

    logger.info("miss markdown %s", link)

    md = MarkItDown()
    result = md.convert(get_article_html_file(link))

    with open(mdfile, "w") as file:
        file.write(result.text_content)

    return result.text_content
