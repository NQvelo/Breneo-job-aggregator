"""
Role families kept by the fetcher for international (English) job feeds.

A listing is kept when its title matches one of these families. Roles outside them
(drivers, cooks, cleaners, security guards, legal, ...) are skipped. Georgian boards
are scoped by their own category IDs in `jobs/fetchers.py` instead, since their titles
are in Georgian.
"""

from __future__ import annotations

import re

SOFTWARE_ENGINEERING = "Software engineering"
DEVOPS_CLOUD = "DevOps & cloud"
DATA_AI = "Data & AI"
DESIGN = "Design"
PRODUCT_BUSINESS_ANALYSIS = "Product & business analysis"
PROJECT_PROGRAM_MANAGEMENT = "Project & program management"
MARKETING = "Marketing"
SALES_SUCCESS = "Sales & success"
FINANCE_ACCOUNTING = "Finance & accounting"
HR_RECRUITING = "HR & recruiting"
CUSTOMER_SUPPORT = "Customer support"
OPERATIONS_ADMIN = "Operations & admin"
HEALTHCARE = "Healthcare"
EDUCATION = "Education"
ENGINEERING_TRADES = "Engineering & trades"
WRITING_MEDIA = "Writing & media"


def _title_re(*patterns: str) -> re.Pattern:
    return re.compile(r"(?i)\b(?:" + "|".join(patterns) + r")\b")


# Checked in order; the first match names the family. Specific families come before
# broad ones so "Data Engineer" is Data & AI, not Engineering & trades.
_ROLE_FAMILIES: list[tuple[str, re.Pattern]] = [
    (
        DATA_AI,
        _title_re(
            r"data\s+(?:scientist|science|engineer(?:ing)?|analyst|analytics|architect|platform|governance|quality)",
            r"machine\s+learning", r"ml(?:ops)?", r"ai", r"a\.i\.", r"artificial\s+intelligence",
            r"deep\s+learning", r"nlp", r"computer\s+vision", r"llms?", r"genai", r"generative",
            r"analytics(?:\s+engineer)?", r"business\s+intelligence", r"bi\s+(?:developer|analyst|engineer)",
            r"statistician", r"quantitative", r"research\s+scientist", r"applied\s+scientist",
            r"prompt\s+engineer", r"data\s+annotat\w*", r"data\s+label\w*",
        ),
    ),
    (
        DEVOPS_CLOUD,
        _title_re(
            r"devops", r"devsecops", r"sre", r"site\s+reliability", r"cloud", r"infrastructure",
            r"platform\s+engineer(?:ing)?", r"sys(?:tems?)?\s*admin\w*", r"systems?\s+engineer",
            r"network\s+(?:engineer|administrator|architect)", r"kubernetes", r"aws", r"azure", r"gcp",
            r"security\s+(?:engineer|analyst|architect|operations)", r"cyber\s*security", r"cyber",
            r"appsec", r"infosec", r"information\s+security", r"soc\s+analyst", r"penetration\s+test\w*",
            r"release\s+engineer", r"build\s+engineer", r"reliability\s+engineer", r"database\s+administrator", r"dba",
        ),
    ),
    (
        SOFTWARE_ENGINEERING,
        _title_re(
            r"software", r"developers?", r"programmers?", r"coders?",
            r"front[\s\-]?end", r"back[\s\-]?end", r"full[\s\-]?stack", r"fullstack",
            r"mobile\s+(?:engineer|developer)", r"ios", r"android", r"react(?:\s+native)?", r"flutter",
            r"web\s+(?:engineer|developer)", r"qa", r"quality\s+assurance", r"sdet",
            r"test(?:ing)?\s+(?:engineer|automation|analyst)", r"automation\s+engineer",
            r"solutions?\s+architect", r"software\s+architect", r"technical\s+architect",
            r"tech(?:nical)?\s+lead", r"engineering\s+manager", r"cto", r"head\s+of\s+engineering",
            r"firmware", r"embedded", r"game\s+(?:developer|engineer|programmer)",
            r"blockchain", r"smart\s+contract", r"solidity",
            r"python", r"java(?:script)?", r"typescript", r"golang", r"rust", r"ruby", r"php",
            r"\.net", r"c\+\+", r"c#", r"node(?:\.js)?", r"salesforce\s+developer",
        ),
    ),
    (
        DESIGN,
        _title_re(
            r"designers?", r"design", r"ux", r"ui", r"ui/ux", r"ux/ui", r"user\s+experience",
            r"user\s+interface", r"illustrator", r"animator", r"motion\s+graphics?", r"art\s+director",
            r"creative\s+director", r"visual\s+(?:designer|artist)", r"3d\s+artist", r"graphic\w*",
            r"user\s+research(?:er)?",
        ),
    ),
    (
        PRODUCT_BUSINESS_ANALYSIS,
        _title_re(
            r"product\s+(?:manager|management|owner|lead|director|analyst|operations|specialist)",
            r"head\s+of\s+product", r"vp\s+(?:of\s+)?product", r"chief\s+product\s+officer", r"cpo",
            r"business\s+(?:analyst|analysis|systems\s+analyst)", r"systems?\s+analyst",
            r"requirements\s+analyst", r"process\s+analyst", r"strategy\s+analyst", r"management\s+consultant",
        ),
    ),
    (
        PROJECT_PROGRAM_MANAGEMENT,
        _title_re(
            r"project\s+(?:manager|management|coordinator|lead|director|officer)",
            r"program(?:me)?\s+(?:manager|management|coordinator|lead|director|officer)",
            r"portfolio\s+manager", r"pmo", r"scrum\s+master", r"agile\s+coach",
            r"delivery\s+(?:manager|lead|director)", r"technical\s+program\s+manager", r"tpm",
        ),
    ),
    (
        MARKETING,
        _title_re(
            r"marketing", r"marketer", r"seo", r"sem", r"ppc", r"growth", r"brand",
            r"demand\s+gen\w*", r"lead\s+gen\w*", r"performance\s+market\w*", r"campaign\w*",
            r"social\s+media", r"community\s+manager", r"communications?", r"public\s+relations",
            r"pr\s+(?:manager|specialist|coordinator)", r"influencer", r"affiliate", r"email\s+marketing",
            r"crm\s+(?:manager|specialist)", r"advertising", r"media\s+buyer",
        ),
    ),
    (
        SALES_SUCCESS,
        _title_re(
            r"sales", r"account\s+(?:executive|manager|director|representative)", r"ae",
            r"business\s+development", r"bdr", r"sdr", r"sales\s+development",
            r"customer\s+success", r"client\s+success", r"partnerships?", r"partner\s+manager",
            r"key\s+account", r"revenue", r"inside\s+sales", r"pre[\s\-]?sales", r"solutions?\s+consultant",
            r"solutions?\s+engineer", r"sales\s+engineer", r"channel\s+manager", r"relationship\s+manager",
            r"alliances?", r"client\s+(?:value\s+)?partner",
        ),
    ),
    (
        FINANCE_ACCOUNTING,
        _title_re(
            r"finance", r"financial", r"accountant", r"accounting", r"bookkeep\w*", r"controller",
            r"comptroller", r"cfo", r"tax", r"audit\w*", r"payroll", r"treasury", r"fp&a",
            r"billing", r"accounts\s+(?:payable|receivable)", r"credit\s+analyst", r"risk\s+analyst",
            r"investment", r"actuar\w*", r"underwrit\w*", r"compliance", r"aml", r"kyc",
            r"grc", r"governance,?\s+risk", r"risk\s+(?:and|&)\s+compliance",
        ),
    ),
    (
        HR_RECRUITING,
        _title_re(
            r"hr", r"human\s+resources", r"recruit\w*", r"talent", r"people\s+(?:operations|ops|partner|team|manager)",
            r"sourcer", r"headhunter", r"hr\s*bp", r"compensation", r"benefits\s+(?:specialist|manager)",
            r"learning\s+and\s+development", r"l&d", r"onboarding\s+specialist",
        ),
    ),
    (
        CUSTOMER_SUPPORT,
        _title_re(
            r"support", r"customer\s+(?:service|care|experience|support)", r"help\s*desk",
            r"service\s+desk", r"call\s+cent(?:er|re)", r"contact\s+cent(?:er|re)", r"chat\s+agent",
            r"client\s+service", r"cx", r"technical\s+support", r"support\s+engineer", r"customer\s+advocate",
        ),
    ),
    (
        OPERATIONS_ADMIN,
        _title_re(
            r"operations", r"ops\s+(?:manager|specialist|associate|analyst)", r"admin\w*",
            r"office\s+manager", r"executive\s+assistant", r"virtual\s+assistant", r"personal\s+assistant",
            r"assistant", r"coordinator", r"secretary", r"receptionist", r"data\s+entry",
            r"procurement", r"purchasing", r"supply\s+chain", r"logistics\s+(?:coordinator|manager|specialist|analyst)",
            r"chief\s+of\s+staff", r"coo", r"general\s+manager", r"business\s+operations", r"facilities",
        ),
    ),
    (
        HEALTHCARE,
        _title_re(
            r"nurse", r"nursing", r"rn", r"lpn", r"physician", r"doctor", r"md", r"medical",
            r"clinical", r"clinician", r"therapist", r"therapy", r"pharmac\w*", r"dental", r"dentist",
            r"health(?:care)?", r"psychologist", r"psychiatr\w*", r"counselor", r"counsellor",
            r"care\s+(?:manager|coordinator)", r"caregiver", r"paramedic", r"radiolog\w*",
            r"veterinar\w*", r"dietitian", r"nutritionist", r"midwife", r"optometrist", r"physiotherap\w*",
        ),
    ),
    (
        EDUCATION,
        _title_re(
            r"teacher", r"teaching", r"tutor", r"instructor", r"lecturer", r"professor",
            r"educat\w*", r"curriculum", r"instructional", r"trainer", r"training\s+(?:specialist|manager)",
            r"academic", r"faculty", r"school", r"esl", r"language\s+(?:teacher|tutor|coach)",
            r"course\s+(?:creator|developer)", r"learning\s+(?:designer|specialist|experience)",
        ),
    ),
    (
        ENGINEERING_TRADES,
        _title_re(
            r"mechanical", r"electrical", r"electronics?", r"civil", r"structural", r"chemical",
            r"industrial", r"manufacturing", r"process\s+engineer", r"hardware", r"mechatronic\w*",
            r"aerospace", r"automotive", r"hvac", r"electrician", r"plumber", r"welder", r"welding",
            r"technician", r"mechanic", r"carpenter", r"machinist", r"cad", r"draft(?:s)?(?:man|sperson|er)",
            r"architect", r"surveyor", r"estimator", r"construction", r"maintenance", r"field\s+engineer",
            r"engineers?", r"engineering",
        ),
    ),
    (
        WRITING_MEDIA,
        _title_re(
            r"writer", r"writing", r"copywriter", r"copy\s*editor", r"editor", r"editorial",
            r"journalist", r"reporter", r"content", r"blogger", r"author", r"proofread\w*",
            r"translator", r"translation", r"interpreter", r"localization", r"localisation",
            r"video\s*(?:editor|producer|grapher)?", r"videographer", r"photographer", r"podcast\w*",
            r"producer", r"media", r"publishing", r"documentation", r"transcri\w*", r"subtitl\w*",
        ),
    ),
]

ROLE_FAMILIES = tuple(label for label, _ in _ROLE_FAMILIES)

# Stack names in the opening of a description still mark an engineering role when
# the title is vague (e.g. "Engineer II", "Member of Technical Staff").
_STACK_HINT = re.compile(
    r"(?i)\b(?:python|javascript|typescript|golang|rust|java|kubernetes|react|node\.js|aws|gcp|azure)\b"
)


def classify_role_family(title: str | None, description: str | None = None) -> str | None:
    """Return the role family for a listing, or None when it is outside every family."""
    text = (title or "").strip()
    if text:
        for label, pattern in _ROLE_FAMILIES:
            if pattern.search(text):
                return label
    head = (description or "")[:800]
    if text and head and _STACK_HINT.search(head) and re.search(r"(?i)\b(?:engineer|developer|staff)\b", text):
        return SOFTWARE_ENGINEERING
    return None


def is_supported_role(job_dict: dict) -> bool:
    return classify_role_family(job_dict.get("title"), job_dict.get("description")) is not None
