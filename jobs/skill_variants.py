"""
Skill names used for matching.

Ported from breneoapp `src/services/matching.ts` (`SKILL_KEYWORDS` and
`normalizeSkillName`). Trim, lowercase, collapse spaces, then this variant map.
Do not add a second map.
"""

from __future__ import annotations

import math
import re

# canonical -> variants. Canonical keys are inserted into the map first, so a
# name that is both a canonical and someone else's variant stays itself
# ("node.js" stays "node.js", not "javascript").
SKILL_KEYWORDS: dict[str, list[str]] = {
    "javascript": ["javascript", "js", "node.js", "nodejs", "react", "vue", "angular"],
    "python": ["python", "django", "flask", "fastapi"],
    "java": ["java", "spring", "spring boot"],
    "c++": ["c++", "cpp", "c plus plus"],
    "c#": ["c#", "csharp", "dotnet", ".net"],
    "go": ["go", "golang"],
    "rust": ["rust"],
    "php": ["php", "laravel", "symfony"],
    "ruby": ["ruby", "rails"],
    "swift": ["swift", "ios"],
    "kotlin": ["kotlin", "android"],
    "typescript": ["typescript", "ts"],
    "html": ["html", "html5"],
    "css": ["css", "css3", "sass", "scss", "tailwind"],
    "sql": ["sql", "mysql", "postgresql", "mongodb", "database"],
    "react": ["react", "reactjs", "react.js"],
    "vue": ["vue", "vuejs", "vue.js"],
    "angular": ["angular", "angularjs"],
    "node.js": ["node.js", "nodejs", "node"],
    "express": ["express", "express.js"],
    "django": ["django"],
    "flask": ["flask"],
    "spring": ["spring", "spring boot"],
    "laravel": ["laravel"],
    "rails": ["rails", "ruby on rails"],
    "git": ["git", "github", "gitlab"],
    "docker": ["docker", "containerization"],
    "kubernetes": ["kubernetes", "k8s"],
    "aws": ["aws", "amazon web services"],
    "azure": ["azure", "microsoft azure"],
    "gcp": ["gcp", "google cloud", "google cloud platform"],
    "linux": ["linux", "unix"],
    "machine learning": ["machine learning", "ml", "deep learning", "neural network"],
    "data science": ["data science", "data analysis", "data analytics"],
    "ai": ["artificial intelligence", "ai", "nlp", "natural language processing"],
    "blockchain": ["blockchain", "ethereum", "solidity", "web3"],
    "devops": ["devops", "ci/cd", "continuous integration"],
    "testing": ["testing", "qa", "quality assurance", "test automation"],
    "ui": ["ui", "user interface", "ux", "user experience"],
    "design": ["design", "figma", "sketch", "adobe"],
    # Role-family skills. Canonical keys are registered first, so these names
    # stay themselves. The catalog stores the display name; matching uses this map.
    "solidity": ["solidity"],
    "firebase": ["firebase"],
    "prisma": ["prisma"],
    "supabase": ["supabase"],
    "electron": ["electron"],
    "webrtc": ["webrtc", "web rtc"],
    "argo cd": ["argo cd", "argocd"],
    "gitops": ["gitops", "git ops"],
    "hashicorp vault": ["hashicorp vault"],
    "istio": ["istio"],
    "cloudflare": ["cloudflare"],
    "tableau": ["tableau"],
    "power bi": ["power bi", "powerbi"],
    "looker": ["looker"],
    "sas": ["sas"],
    "hugging face": ["hugging face", "huggingface"],
    "openai": ["openai"],
    "indesign": ["indesign", "adobe indesign"],
    "canva": ["canva"],
    "framer": ["framer"],
    "webflow": ["webflow"],
    "blender": ["blender"],
    "amplitude": ["amplitude"],
    "mixpanel": ["mixpanel"],
    "user stories": ["user stories", "user story"],
    "bpmn": ["bpmn"],
    "lucidchart": ["lucidchart"],
    "miro": ["miro"],
    "asana": ["asana"],
    "smartsheet": ["smartsheet"],
    "microsoft project": ["microsoft project", "ms project"],
    "pmp": ["pmp"],
    "prince2": ["prince2", "prince 2"],
    "primavera p6": ["primavera p6", "primavera"],
    "seo": ["seo", "search engine optimization"],
    "google analytics": ["google analytics", "ga4"],
    "google ads": ["google ads", "google adwords", "adwords"],
    "hubspot": ["hubspot"],
    "mailchimp": ["mailchimp"],
    "semrush": ["semrush"],
    "ahrefs": ["ahrefs"],
    "meta ads": ["meta ads", "facebook ads"],
    "ppc": ["ppc", "pay per click"],
    "salesforce": ["salesforce", "sfdc"],
    "pipedrive": ["pipedrive"],
    "gong": ["gong"],
    "salesloft": ["salesloft"],
    "meddic": ["meddic"],
    "quickbooks": ["quickbooks", "quickbooks online"],
    "xero": ["xero"],
    "netsuite": ["netsuite", "oracle netsuite"],
    "gaap": ["gaap"],
    "ifrs": ["ifrs"],
    "financial modeling": ["financial modeling", "financial modelling"],
    "sap": ["sap"],
    "anaplan": ["anaplan"],
    "greenhouse": ["greenhouse"],
    "bamboohr": ["bamboohr", "bamboo hr"],
    "workday": ["workday"],
    "linkedin recruiter": ["linkedin recruiter"],
    "icims": ["icims"],
    "zendesk": ["zendesk"],
    "freshdesk": ["freshdesk"],
    "intercom": ["intercom"],
    "servicenow": ["servicenow", "service now"],
    "coupa": ["coupa"],
    "concur": ["concur", "sap concur"],
    "expensify": ["expensify"],
    "procurement": ["procurement"],
    "supply chain": ["supply chain", "supply-chain"],
    "hipaa": ["hipaa"],
    "cerner": ["cerner"],
    "epic ehr": ["epic ehr", "epic emr", "epic systems"],
    "icd-10": ["icd-10", "icd 10"],
    "medical coding": ["medical coding"],
    "athenahealth": ["athenahealth", "athena health"],
    "moodle": ["moodle"],
    "blackboard": ["blackboard"],
    "canvas lms": ["canvas lms", "instructure canvas"],
    "curriculum development": ["curriculum development"],
    "instructional design": ["instructional design"],
    "tesol": ["tesol"],
    "celta": ["celta"],
    "autocad": ["autocad", "auto cad"],
    "solidworks": ["solidworks", "solid works"],
    "revit": ["revit"],
    "plc": ["plc"],
    "cnc": ["cnc"],
    "bim": ["bim"],
    "ansys": ["ansys"],
    "catia": ["catia"],
    "copywriting": ["copywriting", "copy writing"],
    "technical writing": ["technical writing"],
    "premiere pro": ["premiere pro", "adobe premiere"],
    "final cut pro": ["final cut pro", "final cut"],
    "davinci resolve": ["davinci resolve", "da vinci resolve"],
    "ap style": ["ap style"],
    "westlaw": ["westlaw"],
    "lexisnexis": ["lexisnexis", "lexis nexis"],
    "contract drafting": ["contract drafting"],
    "gdpr": ["gdpr"],
    "ediscovery": ["ediscovery", "e-discovery"],
    "due diligence": ["due diligence"],
    "market sizing": ["market sizing"],
    "operating model": ["operating model"],
    "commercial due diligence": ["commercial due diligence"],
    "mece": ["mece"],
}

VARIANT_TO_CANONICAL: dict[str, str] = {}
for _canonical in SKILL_KEYWORDS:
    _key = _canonical.lower().strip()
    VARIANT_TO_CANONICAL[_key] = _canonical
for _canonical, _variants in SKILL_KEYWORDS.items():
    for _variant in _variants:
        _key = _variant.lower().strip()
        if _key not in VARIANT_TO_CANONICAL:
            VARIANT_TO_CANONICAL[_key] = _canonical

_SPACE_RE = re.compile(r"\s+")


def _match_text(value) -> str:
    """Same coercion as matching.ts `asMatchText`."""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return ""
        return str(value)
    if isinstance(value, list):
        parts = [_match_text(item).strip() for item in value]
        return ", ".join(part for part in parts if part)
    return ""


def normalize_skill_name(value) -> str:
    """Trim, lowercase, collapse spaces, then the variant map."""
    key = _SPACE_RE.sub(" ", _match_text(value).lower().strip())
    if not key:
        return ""
    return VARIANT_TO_CANONICAL.get(key, key)


def normalize_skill_list(skills) -> list[str]:
    """Normalize, drop empties, dedupe. First occurrence wins."""
    if not isinstance(skills, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in skills:
        name = normalize_skill_name(item)
        if name and name not in seen:
            seen.add(name)
            normalized.append(name)
    return normalized


def has_stored_skills(skills) -> bool:
    """True when the job already has at least one non-blank skill string."""
    if not isinstance(skills, list):
        return False
    return any(isinstance(item, str) and item.strip() for item in skills)
