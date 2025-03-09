import uuid


def guid(link: str) -> str:
    return f'{uuid.uuid5(uuid.NAMESPACE_URL, link)}'
