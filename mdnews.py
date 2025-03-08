from rss_parser import RSSParser
from rss_parser.models.rss import RSS
from requests import get
from email.utils import parsedate_to_datetime
import mimetypes
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
from urllib.parse import urljoin
from PIL import Image
import subprocess

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

    def markdown_details(self):
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

    def markdown(self):
        file = io.StringIO()
        file.write(f'# {self.title}\n\n')
        if self.image:
            file.write(f'![]({self.image})\n')
        file.write(f'\n*{self.date.date()} - {self.attr}*\n\n')
        file.write(f'*{self.description}*\n\n')
        file.write(f'{self.content}')
        file.write(f'\n*{self.guid}*\n')
        file.write('\n---\n\n')
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


def parse_feed(rss: RSS) -> list[Article]:
    arts = list()

    for item in rss.channel.items:
        if not item.links:
            continue

        art = parse_item(item)
        art.attr = rss.channel.title.content

        arts.append(art)

    arts.sort()

    return arts


def download_and_parse(feed, dir) -> list[Article]:
    response = get(feed.get("url"))
    rss = RSSParser.parse(response.text)

    with open(os.path.join(dir, feed.get("name") + ".yaml"), "w") as file:
        file.write(yaml.dump(rss.dict_plain()))

    return parse_feed(rss)


def download_all(filename: str, dir: str) -> list[Article]:
    feeds = None
    with open(filename, 'r') as f:
        feeds = list(yaml.load(f, Loader=yaml.SafeLoader))

    arts = list()

    for feed in feeds:
        if feed.get("skip"):
            continue
        arts.extend(download_and_parse(feed, dir))

    arts.sort()
    return arts


def get_article_html_file(article: Article) -> str:
    htmlfile = os.path.join("build", "cache", str(article.guid) + ".html")

    if os.path.exists(htmlfile):
        return htmlfile

    logger.info("miss html", article.link)

    response = get(article.link)
    with open(htmlfile, "w") as file:
        file.write(response.text)

    return htmlfile


def get_article_markdown(article: Article) -> str:
    mdfile = os.path.join("build", "cache", str(article.guid) + ".md")

    if os.path.exists(mdfile):
        with open(mdfile) as file:
            return file.read()

    logger.info("miss markdown", article.link)

    md = MarkItDown()
    result = md.convert(get_article_html_file(article))

    with open(mdfile, "w") as file:
        file.write(result.text_content)

    return result.text_content


def download_images(art: Article):
    images = re.findall(
        r'!\[((?:[^\]\\]|\\.)*)\]\(((?:[^)\\]|\\.)*)\)', art.content)
    if art.image:
        images.append(("", art.image))

    if not images:
        return

    mapping = {}

    for image in images:
        loc = image[1]
        guid = uuid.uuid5(uuid.NAMESPACE_URL, loc)

        try:
            response = get(loc)
        except:
            continue

        ctype = response.headers.get("Content-Type")

        ext = mimetypes.guess_extension(ctype)
        if not ext or ext not in [".jpg", ".png", ".gif"]:
            if ctype.endswith("webp"):
                ext = ".webp"
            else:
                continue

        with open(os.path.join("build", "cache", str(guid) + ext), "wb") as file:
            file.write(response.content)

        img = Image.open(io.BytesIO(response.content))
        if img.mode == 'RGBA':
            bg = Image.new('RGB', img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg

        size = img.size
        if size[0] > 1024:
            img.thumbnail(
                (1024, round(size[1]*1024/size[0])), Image.Resampling.LANCZOS)

        img = img.convert('RGB')

        output = io.BytesIO()

        img.save(output, format='JPEG', quality="web_medium",
                 optimize=True, progressive=True)

        outfile = str(guid) + ".jpg"

        with open(os.path.join("build", "htdocs", outfile), "wb") as file:
            file.write(output.getvalue())

        mapping[image[1]] = outfile

    for key, value in mapping.items():
        art.content = art.content.replace(key, value)

    if art.image and art.image in mapping:
        art.image = mapping[art.image]


def convert_content(art: Article) -> str:
    text = get_article_markdown(art)

    p = re.compile(r"\[Tovább.a.rovat[^\)]*\)", re.MULTILINE+re.DOTALL)
    m = p.search(text)
    if m == None:
        p = re.compile(r"Kövesse az Indexet.*facebook.com/Indexhu\)",
                       re.MULTILINE+re.DOTALL)
        m = p.search(text)
        if m == None:
            p = re.compile(
                r"\[(Belföld|Külföld|After|Gazdaság|Sport|Techtud|Gasztro|English)\].*\)")
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

    return text


htdocs_dir = os.path.join("build", "htdocs")
cache_dir = os.path.join("build", "cache")
feed_dir = os.path.join("build", "feed")

os.makedirs(name=cache_dir, exist_ok=True)
os.makedirs(name=htdocs_dir, exist_ok=True)
os.makedirs(name=feed_dir, exist_ok=True)
shutil.copy("index.html", htdocs_dir)
shutil.copy("newspaper.svg", htdocs_dir)

arts = download_all("feeds.yml", feed_dir)


def write_cover(date: datetime.datetime):
    cover = os.path.join(htdocs_dir, "cover.svg")
    icon = os.path.join(htdocs_dir, "newspaper.svg")

    with open(icon) as file:
        svg = file.read().replace("YYYY-MM-DD", f'{date.date()}')

    with open(cover, "w") as file:
        file.write(svg.replace("YYYY-MM-DD", f'{date.date()}'))


def write_ebook(date: datetime.datetime):
    subprocess.run(["pandoc", "--epub-cover-image=cover.svg", "--toc",
                   "--toc-depth=1", "-o", f"news-{date.date()}.epub", "--from=markdown",  "--to=epub",  "news.md"], cwd=htdocs_dir)


with open(os.path.join(htdocs_dir, "news.md"), "w") as out:
    day = datetime.date.today()
    id = uuid.uuid5(uuid.NAMESPACE_URL, f"{day}")
    out.write(
        f"""---
title:
  - type: main
    text: {day}
identifier:
  - scheme: URN
    text: urn:uuid:{id}
belongs-to-collection: mdnews
---

""")

    for art in arts:
        art.content = convert_content(art)
        download_images(art)

        out.write(art.markdown())

with open(os.path.join(htdocs_dir, "README.md"), "w") as out:
    day = datetime.date.today()
    out.write(f'## {day}\n\n')

    for art in arts:
        date = art.date.date()
        if day != date:
            out.write(f'## {date}\n\n')
            day = date

        out.write(art.markdown_details())

today = datetime.datetime.today()

write_cover(today)
write_ebook(today)
