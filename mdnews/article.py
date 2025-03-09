import uuid
from dataclasses import dataclass
import datetime
import io
import logging

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
    format: str = ""
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
