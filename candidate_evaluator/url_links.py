"""Extract candidate-shared links locally, retaining source paths."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

OUTPUT_COLUMNS = [
    "Candidate", "Profile URL", "Link Found", "GitHub URLs",
    "Website / Portfolio URLs", "Project / Demo URLs", "Other URLs", "URL Sources",
]
# Metadata contains provider-generated URLs, rather than candidate-shared work.
EXCLUDED = {
    "moreprofiles", "interests", "companylogo", "schoollogo", "profilepicture",
    "profilephoto", "photo", "image", "images", "sizes", "backgroundpicture",
    "certifications", "licenses", "skills", "topskills", "location", "languages",
    "startdate", "enddate", "registeredat", "education", "recommendations",
}
METADATA_KEYS = {
    "linkedinurl", "companylinkedinurl", "schoollinkedinurl", "associatedwithlink",
    "companyurl", "companywebsite", "companyname", "companyuniversalname",
    "associatedwith", "schoolname", "logourl", "pictureurl", "avatar", "avatarurl",
}
URL_PATTERN = re.compile(
    r"(?:https?://|www\.)[^\s<>\"']+|"
    r"(?<![\w@/])(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?\.)+"
    r"(?:com|org|net|io|dev|app|me|ai|co|in|tech|site|xyz|pages|design|bio)"
    r"(?![a-zA-Z0-9.-])(?:/[^\s<>\"']*)?", re.IGNORECASE,
)


def extract_links(profile):
    """Walk original fields. Send no profile data to a model."""
    found = {}

    def visit(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                lower = key.casefold().replace("_", "")
                if lower in EXCLUDED or lower in METADATA_KEYS:
                    continue
                visit(child, f"{path}.{key}" if path else key)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")
        elif isinstance(value, str):
            for match in URL_PATTERN.finditer(value):
                original = match.group().rstrip(".,;:!?")
                while original.endswith(")") and original.count(")") > original.count("("):
                    original = original[:-1]
                try:
                    parsed = urlsplit(original if "://" in original else "https://" + original)
                    host = (parsed.hostname or "").lower()
                    port = parsed.port
                except ValueError:
                    continue
                if not host or host == "linkedin.com" or host.endswith(".linkedin.com"):
                    continue
                if host == "licdn.com" or host.endswith(".licdn.com"):
                    continue
                # Host matching is case-insensitive. Preserve path/query case and parameters.
                identity = (host, port, parsed.path.rstrip("/"), parsed.query, parsed.fragment)
                entry = found.setdefault(identity, {"url": original, "sources": [], "category": classify(host, path)})
                if path not in entry["sources"]:
                    entry["sources"].append(path)
    visit(profile, "")
    return list(found.values())


def classify(host, path):
    if host == "github.com" or host.endswith(".github.com"):
        return "GitHub URLs"
    if re.search(r"(?:^|\.)(?:websites?|contact_info|contactInfo|portfolio)(?:[.\[]|$)", path):
        return "Website / Portfolio URLs"
    if re.search(r"(?:^|\.)projects?(?:[.\[]|$)", path):
        return "Project / Demo URLs"
    if host.endswith((".github.io", ".pages.dev", ".vercel.app", ".netlify.app")):
        return "Website / Portfolio URLs"
    return "Other URLs"


def evaluate(candidate):
    entries = candidate.get("url_entries", [])
    row = {column: "" for column in OUTPUT_COLUMNS}
    row.update({"Candidate": candidate.get("candidate_name", ""),
                "Profile URL": candidate.get("linkedin_url", ""),
                "Link Found": int(bool(entries))})
    for column in OUTPUT_COLUMNS[3:-1]:
        row[column] = "\n".join(entry["url"] for entry in entries if entry["category"] == column)
    row["URL Sources"] = "\n".join(
        entry["url"] + " — " + ", ".join(entry["sources"]) for entry in entries
    ) or "No qualifying link found in supplied JSON."
    return row
