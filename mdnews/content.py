import datetime
import re
import os
import shutil
import subprocess
import logging
import io
import mimetypes
from requests import get
from PIL import Image

from .article import Article
from .cache import get_article_markdown
from .guid import guid

logger = logging.getLogger(__name__)

content_dir = os.path.join("build", "content")
os.makedirs(name=content_dir, exist_ok=True)


def remove_links(text: str) -> str:
    return re.subn(r'(?<!!)\[([^]]+)\]\([^)]+\)', r'\1', text)[0]


def convert_content(art: Article) -> str:
    text = get_article_markdown(art.link)

    p = re.compile(r"\[Tovább.a.rovat[^\)]*\)", re.MULTILINE+re.DOTALL)
    m = p.search(text)
    if m == None:
        p = re.compile(r"Kövesse az Indexet.*facebook.com/Indexhu\)",
                       re.MULTILINE+re.DOTALL)
        m = p.search(text)
        if m == None:
            p = re.compile(
                r"\[(Belföld|Külföld|After|Gazdaság|Sport|Techtud|Gasztro|Észkombájn|Életmód|Zacc|Podcast|KultEnglish)\].*\)")
            m = p.search(text)
            if m == None:
                p = re.compile(r"\!\[Index.hu[^\)]*\)",
                               re.MULTILINE+re.DOTALL)
                m = p.search(text)
                if m == None:
                    p = re.compile(r"[^#]# .*", re.MULTILINE)
                    m = p.search(text)
                    if m == None:
                        p = re.compile(r"!\[Véleményhírlevél.*", re.MULTILINE)
                        m = p.search(text)
                        if m == None:
                            p = re.compile(
                                r"Vágólapra másolva.*", re.MULTILINE)
                            m = p.search(text)
                            if m == None:
                                p = re.compile(r"[^#]# .*", re.MULTILINE)
                                m = p.search(text)

    if m != None:
        text = text[m.span()[1]:]

    p = re.compile(r"Galéria: .*", re.MULTILINE)  # index or telex?
    text = p.sub("", text)
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
    p = re.compile(r"!\[Véleményhírlevél.*", re.MULTILINE)
    text = p.sub("", text)

    return remove_links(text)


def download_images(art: Article):
    images = re.findall(
        r'!\[((?:[^\]\\]|\\.)*)\]\(((?:[^)\\]|\\.)*)\)', art.content)
    if art.image:
        images.append(("", art.image))

    if not images:
        return

    mapping = {}

    errimg = "missing-image.jpg"

    for image in images:
        loc = image[1]
        outfile = guid(loc) + ".jpg"
        outfile_abs = os.path.join(content_dir, outfile)

        if os.path.exists(outfile_abs):
            mapping[image[1]] = outfile
            continue

        logger.info("downloading image %s", loc)

        try:
            response = get(loc)
        except:
            mapping[image[1]] = errimg
            continue

        ctype = response.headers.get("Content-Type")

        ext = mimetypes.guess_extension(ctype)
        if not ext or ext not in [".jpg", ".png", ".gif"]:
            if ctype.endswith("webp"):
                ext = ".webp"
            else:
                continue

        with open(os.path.join("build", "cache", guid(loc) + ext), "wb") as file:
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

        with open(outfile_abs, "wb") as file:
            file.write(output.getvalue())

        mapping[image[1]] = outfile

    for key, value in mapping.items():
        art.content = art.content.replace(key, value)

    if art.image and art.image in mapping:
        art.image = mapping[art.image]

    art.content = re.subn(
        r"\!\[[^]]*\]\("+errimg+"\)", "", art.content, flags=re.DOTALL+re.MULTILINE)[0]


def __write_cover(date: datetime.datetime):
    shutil.copy("newspaper.svg", content_dir)

    cover = os.path.join(content_dir, "cover.svg")
    icon = os.path.join(content_dir, "newspaper.svg")

    with open(icon) as file:
        svg = file.read().replace("YYYY-MM-DD", f'{date.date()}')

    with open(cover, "w") as file:
        file.write(svg.replace("YYYY-MM-DD", f'{date.date()}'))


def __write_ebook(date: datetime.datetime):
    subprocess.run(["pandoc", "--epub-cover-image=cover.svg", "--toc",
                   "--toc-depth=1", "-o", f"news-{date.date()}.epub", "--from=markdown",  "--to=epub",  "news.md"], cwd=content_dir)


def __render_ebook(day: datetime.datetime, arts: list[Article]):
    __write_cover(day)

    with open(os.path.join(content_dir, "news.md"), "w") as out:
        out.write(
            f"""---
title:
  - type: main
    text: {day.date()}
identifier:
  - scheme: URN
    text: urn:uuid:{guid(day.date().isoformat())}
belongs-to-collection: mdnews
---

""")

        for art in arts:
            out.write(art.markdown())


def __render_page(date: datetime.datetime, arts: list[Article]):
    shutil.copy("index.html", content_dir)

    with open(os.path.join(content_dir, "README.md"), "w") as out:
        out.write(f'## {date.date()}\n\n')

        for art in arts:
            if date.date() != art.date.date():
                date = art.date
                out.write(f'## {date.date().isoformat()}\n\n')

            out.write(art.markdown_details())


today = datetime.datetime.today()


def render(day: datetime.datetime, arts: list[Article]):
    __render_ebook(day, arts)
    __render_page(today, arts)
    __write_ebook(today)
