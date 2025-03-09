from rss_parser import RSSParser
from rss_parser.models.rss import RSS
from requests import get
from email.utils import parsedate_to_datetime
import yaml
import os
import logging

from .article import Article
from .guid import guid
from .content import convert_content, download_images

logger = logging.getLogger(__name__)

feed_dir = os.path.join("build", "feed")
os.makedirs(name=feed_dir, exist_ok=True)


def __parse_item(format, item) -> Article:
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

    art = Article(title=title, description=description, link=link,
                  date=date, image=image, guid=guid(link), format=format)

    art.content = convert_content(art)

    download_images(art)

    return art


def __parse_feed(format: str, rss: RSS) -> list[Article]:
    arts = list()

    for item in rss.channel.items:
        if not item.links:
            continue

        art = __parse_item(format, item)
        art.attr = rss.channel.title.content

        arts.append(art)

    arts.sort()

    return arts


def __download_and_parse(feed) -> list[Article]:
    response = get(feed.get("url"))
    rss = RSSParser.parse(response.text)

    with open(os.path.join(feed_dir, feed.get("name") + ".yaml"), "w") as file:
        file.write(yaml.dump(rss.dict_plain()))

    return __parse_feed(feed.get("format"), rss)


def download_feeds(filename: str) -> list[Article]:
    feeds = None
    with open(filename, 'r') as f:
        feeds = list(yaml.load(f, Loader=yaml.SafeLoader))

    arts = list()

    for feed in feeds:
        if feed.get("skip"):
            continue
        arts.extend(__download_and_parse(feed))

    arts.sort()
    return arts
