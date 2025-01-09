from rss_parser import RSSParser
from requests import get
from email.utils import parsedate_to_datetime
import uuid
from dataclasses import dataclass
import datetime
import io
import yaml
import os
from markitdown import MarkItDown
import re
import logging
import shutil

logger = logging.getLogger(__name__)


@dataclass
class Article:
    title: str
    description: str
    link: str
    date: datetime.datetime
    image: str
    guid: uuid.UUID
    attr: str = ""
    content: str = ""

    def __lt__(self, other):
        return self.date > other.date

    def markdown(self):
        file = io.StringIO()
        file.write("<details><summary><strong>")
        file.write(f'{self.title}')
        file.write("</strong></summary>\n\n")
        if self.image:
            file.write(f'![]({self.image})\n\n')
        file.write(f'{self.content}\n')
        file.write(f'\n<small>{self.guid}</small>\n')
        file.write("\n</details>\n\n")
        file.write(f'*{self.description}*\n\n')
        file.write(
            f'<small>{self.date.date()} - {self.attr}</small>\n')
        file.write('\n---\n')
        result = file.getvalue()
        file.close()
        return result


def parse_item(item) -> Article:
    title = item.title.content
    description = item.description.content if item.description else ""
    link = item.links[-1].content

    found = None
    for enc in item.enclosures:
        if not found or int(found.attributes.get("length", "0")) <= int(enc.attributes.get("length", "0")):
            found = enc

    image = ""
    if found:
        image = found.attributes.get('url')

    date = parsedate_to_datetime(item.pub_date.content)

    guid = None
    if item.guid:
        try:
            guid = uuid.UUID(item.guid.content)
        except ValueError:

            pass
    if not guid:
        if item.guid:
            guid = uuid.uuid5(uuid.NAMESPACE_URL, item.guid.content)
        else:
            guid = uuid.uuid5(uuid.NAMESPACE_URL, link)

    return Article(title=title, description=description, link=link, date=date, image=image, guid=guid)


def parse_feed(text: str) -> list[Article]:
    arts = list()

    rss = RSSParser.parse(text)

    for item in rss.channel.items:
        if not item.links:
            continue

        art = parse_item(item)
        art.attr = rss.channel.title.content

        arts.append(art)

    arts.sort()

    return arts


def download_and_parse(rss_url) -> list[Article]:
    response = get(rss_url)
    return parse_feed(response.text)


def download_all(filename: str) -> list[Article]:
    feeds = None
    with open(filename, 'r') as f:
        feeds = list(yaml.load(f, Loader=yaml.SafeLoader))

    arts = list()

    for feed in feeds:
        if feed.get("skip"):
            continue
        arts.extend(download_and_parse(feed["url"]))

    arts.sort()
    return arts


def get_article_html_file(article: Article) -> str:
    filename = os.path.join("build", "cache", str(article.guid) + ".html")

    if os.path.exists(filename):
        return filename

    logger.info("miss", article.link)

    response = get(article.link)
    with open(filename, "w") as file:
        file.write(response.text)

    return filename


def convert_content(art: Article) -> str:
    filename = get_article_html_file(art)
    md = MarkItDown()
    result = md.convert(filename)

    text = result.text_content

    p = re.compile(r"\[Tovább.a.rovat[^\)]*\)", re.MULTILINE+re.DOTALL)
    m = p.search(text)
    if m == None:
        p = re.compile(r"\!\[Index.hu[^\)]*\)", re.MULTILINE+re.DOTALL)
        m = p.search(text)
        if m == None:
            p = re.compile(r"\!\[Véleményhírlevél.*", re.MULTILINE)
            m = p.search(text)
            if m == None:
                p = re.compile(r"Vágólapra másolva.*", re.MULTILINE)
                m = p.search(text)
                if m == None:
                    p = re.compile(r"# .*", re.MULTILINE)
                    m = p.search(text)

    if m != None:
        text = text[m.span()[1]:]

    p = re.compile(
        r"(\[\!\[Index könyvek.*|\!\[Zöld Index).*|\[Akták.*|\!\[Index.hu[^\)]*\).*", re.DOTALL + re.MULTILINE)
    text = p.sub("", text)
    p = re.compile(r"\*\([^\)]+\).*", re.DOTALL+re.MULTILINE)
    text = p.sub("", text)
    p = re.compile(r"## A téma legfrissebb hírei.*", re.DOTALL+re.MULTILINE)
    text = p.sub("", text)
    p = re.compile(
        r"> \[A bejegyzés megtekintése az Instagramon.*", re.DOTALL+re.MULTILINE)
    text = p.sub("", text)
    p = re.compile(r"\[\!\[Google News.*", re.DOTALL+re.MULTILINE)
    text = p.sub("", text)
    p = re.compile(r"#### További [^\n]* híreink.*", re.DOTALL+re.MULTILINE)
    text = p.sub("", text)
    p = re.compile(
        r"[ ]{,4}\[Kedvenceink.*|[ ]{,4}\[Kapcsolódó.*", re.DOTALL+re.MULTILINE)
    text = p.sub("", text)
    p = re.compile(r"\*?Via \[.*", re.DOTALL+re.MULTILINE)
    text = p.sub("", text)
    p = re.compile(
        r"\[\!\[\]\(https://www.hwsw.hu/img/icons/facebook.svg\).*", re.DOTALL+re.MULTILINE)
    text = p.sub("", text)

    with open(os.path.join("build", "cache", str(art.guid) + "-md"), "w") as file:
        file.write(result.text_content)

    return text


htdocs_dir = os.path.join("build", "htdocs")
cache_dir = os.path.join("build", "cache")

os.makedirs(name=cache_dir, exist_ok=True)
os.makedirs(name=htdocs_dir, exist_ok=True)
shutil.copy("index.html", htdocs_dir)
shutil.copy("mdnews.png", htdocs_dir)

arts = download_all("feeds.yml")

with open(os.path.join(htdocs_dir, "README.md"), "w") as out:
    day = datetime.date.today()
    out.write(f'## {day}\n\n')

    for art in arts:
        art.content = convert_content(art)
        date = art.date.date()
        if day != date:
            out.write(f'## {date}\n\n')
            day = date

        out.write(art.markdown())
