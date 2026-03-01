from typing import Tuple


def compare_skills(user_skills: list[str], required_skills: list[str]) -> Tuple[list[str], list[str]]:
    """Return (existing, missing) lists given user's skills and required skills."""
    user_set = {s.lower() for s in user_skills}
    existing = [s for s in required_skills if s.lower() in user_set]
    missing = [s for s in required_skills if s.lower() not in user_set]
    return existing, missing
