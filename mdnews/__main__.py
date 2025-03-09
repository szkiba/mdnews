import datetime

from .feed import download_feeds
from .content import render

if __name__ == '__main__':
    render(datetime.datetime.today(), download_feeds("feeds.yml"))
