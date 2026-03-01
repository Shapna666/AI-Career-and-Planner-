import re


def extract_skills(text: str, possible_skills: list[str]) -> list[str]:
    """Return a list of skills found in `text` by simple keyword matching.

    `possible_skills` is a list of skill names we want to look for; the
    comparison is case‑insensitive and matches whole words.
    """
    found = set()
    lower = text.lower()
    for skill in possible_skills:
        pattern = r"\b" + re.escape(skill.lower()) + r"\b"
        if re.search(pattern, lower):
            found.add(skill)
    return sorted(found)
