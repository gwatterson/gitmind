def normalize_tag(tag: str) -> str:
    return tag.strip().lower().replace(" ", "-")


def add_tags(new_tags: list[str], existing: list[str] = []) -> list[str]:
    for tag in new_tags:
        tag = normalize_tag(tag)
        if tag not in existing:
            existing.append(tag)
    return existing
