from typing import Dict, List


def generate_roadmap(missing_skills: List[str]) -> Dict[str, str]:
    """Create a simple weekly roadmap mapping weeks to skill topics."""
    roadmap = {}
    for idx, skill in enumerate(missing_skills, start=1):
        roadmap[f"Week {idx}"] = skill
    return roadmap
