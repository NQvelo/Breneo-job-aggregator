"""
Roles a candidate can choose on the frontend /start page.

Copied from breneoapp `src/onboarding/onboardingAnswers.ts` (`ONBOARDING_ROLE_IDS`
and English titles) and `src/locales/ka.ts` (Georgian titles). Each slug gets its
own row in `InterviewRole` and its own prepared questions.
"""

from __future__ import annotations

import re
import unicodedata

# slug, English title, Georgian title
INTERVIEW_ROLES: tuple[tuple[str, str, str], ...] = (
    ("react", "React Developer", "React დეველოპერი"),
    ("frontend", "Frontend Engineer", "Frontend ინჟინერი"),
    ("backend", "Backend Engineer", "Backend ინჟინერი"),
    ("fullstack", "Full Stack Engineer", "Full Stack ინჟინერი"),
    ("mobile", "Mobile Engineer", "მობილური ინჟინერი"),
    ("ios", "iOS Developer", "iOS დეველოპერი"),
    ("android", "Android Developer", "Android დეველოპერი"),
    ("web", "Web Developer", "ვებ დეველოპერი"),
    ("embedded", "Embedded Software Engineer", "ჩაშენებული სისტემების ინჟინერი"),
    ("game", "Game Developer", "თამაშების დეველოპერი"),
    ("qa", "QA Engineer", "QA ინჟინერი"),
    ("qa_auto", "Test Automation Engineer", "ტესტირების ავტომატიზაციის ინჟინერი"),
    ("eng_manager", "Engineering Manager", "ინჟინერიის მენეჯერი"),
    ("devops", "DevOps Engineer", "DevOps ინჟინერი"),
    ("cloud", "Cloud Engineer", "Cloud ინჟინერი"),
    ("sre", "Site Reliability Engineer", "Site Reliability ინჟინერი"),
    ("sysadmin", "Systems Administrator", "სისტემური ადმინისტრატორი"),
    ("platform", "Platform Engineer", "პლატფორმის ინჟინერი"),
    ("security", "Security Engineer", "უსაფრთხოების ინჟინერი"),
    ("network", "Network Engineer", "ქსელის ინჟინერი"),
    ("data_analyst", "Data Analyst", "მონაცემთა ანალიტიკოსი"),
    ("data_scientist", "Data Scientist", "მონაცემთა მეცნიერი"),
    ("data_engineer", "Data Engineer", "მონაცემთა ინჟინერი"),
    ("ml", "Machine Learning Engineer", "Machine Learning ინჟინერი"),
    ("ai", "AI Engineer", "AI ინჟინერი"),
    ("bi", "Business Intelligence Analyst", "ბიზნეს ინტელექტის ანალიტიკოსი"),
    ("product_designer", "Product Designer", "პროდუქტის დიზაინერი"),
    ("ux", "UX Designer", "UX დიზაინერი"),
    ("ui", "UI Designer", "UI დიზაინერი"),
    ("graphic", "Graphic Designer", "გრაფიკული დიზაინერი"),
    ("motion", "Motion Designer", "Motion დიზაინერი"),
    ("product_manager", "Product Manager", "პროდუქტის მენეჯერი"),
    ("business_analyst", "Business Analyst", "ბიზნეს ანალიტიკოსი"),
    ("product_owner", "Product Owner", "პროდუქტის მფლობელი"),
    ("product_ops", "Product Operations", "პროდუქტის ოპერაციები"),
    ("project_manager", "Project Manager", "პროექტის მენეჯერი"),
    ("program_manager", "Program Manager", "პროგრამის მენეჯერი"),
    ("scrum", "Scrum Master", "Scrum Master"),
    ("pmo", "PMO Analyst", "PMO ანალიტიკოსი"),
    ("digital_marketing", "Digital Marketing Specialist", "ციფრული მარკეტინგის სპეციალისტი"),
    ("performance", "Performance Marketing Manager", "შედეგზე ორიენტირებული მარკეტინგი"),
    ("content_marketing", "Content Marketing Manager", "კონტენტ მარკეტინგის მენეჯერი"),
    ("brand", "Brand Manager", "ბრენდის მენეჯერი"),
    ("seo", "SEO Specialist", "SEO სპეციალისტი"),
    ("social", "Social Media Manager", "სოციალური მედიის მენეჯერი"),
    ("account_executive", "Account Executive", "გაყიდვების მენეჯერი"),
    ("sdr", "Sales Development Representative", "გაყიდვების განვითარების წარმომადგენელი"),
    ("customer_success", "Customer Success Manager", "მომხმარებლის წარმატების მენეჯერი"),
    ("account_manager", "Account Manager", "ანგარიშის მენეჯერი"),
    ("bdr", "Business Development Representative", "ბიზნესის განვითარების წარმომადგენელი"),
    ("accountant", "Accountant", "ბუღალტერი"),
    ("financial_analyst", "Financial Analyst", "ფინანსური ანალიტიკოსი"),
    ("bookkeeper", "Bookkeeper", "ბუღალტრული აღრიცხვა"),
    ("controller", "Financial Controller", "ფინანსური კონტროლერი"),
    ("auditor", "Auditor", "აუდიტორი"),
    ("recruiter", "Recruiter", "რეკრუტერი"),
    ("hr_generalist", "HR Generalist", "HR გენერალისტი"),
    ("talent", "Talent Acquisition Specialist", "ნიჭის მოძიების სპეციალისტი"),
    ("people_ops", "People Operations", "People Operations"),
    ("support_specialist", "Customer Support Specialist", "მხარდაჭერის სპეციალისტი"),
    ("support_lead", "Customer Support Lead", "მხარდაჭერის ხელმძღვანელი"),
    ("technical_support", "Technical Support Specialist", "ტექნიკური მხარდაჭერა"),
    ("success_associate", "Customer Success Associate", "მომხმარებლის წარმატების სპეციალისტი"),
    ("operations_manager", "Operations Manager", "ოპერაციების მენეჯერი"),
    ("office_manager", "Office Manager", "ოფისის მენეჯერი"),
    ("executive_assistant", "Executive Assistant", "აღმასრულებელი ასისტენტი"),
    ("admin", "Administrative Assistant", "ადმინისტრაციული ასისტენტი"),
    ("nurse", "Nurse", "ექთანი"),
    ("physician", "Physician", "ექიმი"),
    ("medical_assistant", "Medical Assistant", "სამედიცინო ასისტენტი"),
    ("healthcare_admin", "Healthcare Administrator", "ჯანდაცვის ადმინისტრატორი"),
    ("pharmacist", "Pharmacist", "ფარმაცევტი"),
    ("teacher", "Teacher", "მასწავლებელი"),
    ("tutor", "Tutor", "რეპეტიტორი"),
    ("instructional", "Instructional Designer", "სასწავლო დიზაინერი"),
    ("academic", "Academic Coordinator", "აკადემიური კოორდინატორი"),
    ("mechanical", "Mechanical Engineer", "მექანიკოსი ინჟინერი"),
    ("electrical", "Electrical Engineer", "ელექტრო ინჟინერი"),
    ("civil", "Civil Engineer", "სამოქალაქო ინჟინერი"),
    ("technician", "Technician", "ტექნიკოსი"),
    ("electrician", "Electrician", "ელექტრიკოსი"),
    ("content_writer", "Content Writer", "კონტენტის ავტორი"),
    ("copywriter", "Copywriter", "ქოფირაიტერი"),
    ("journalist", "Journalist", "ჟურნალისტი"),
    ("editor", "Editor", "რედაქტორი"),
    ("video", "Video Producer", "ვიდეო პროდიუსერი"),
    ("lawyer", "Lawyer", "იურისტი"),
    ("paralegal", "Paralegal", "იურისტის ასისტენტი"),
    ("compliance", "Compliance Specialist", "შესაბამისობის სპეციალისტი"),
    ("legal_counsel", "Legal Counsel", "იურიდიული მრჩეველი"),
    ("consultant", "Consultant", "კონსულტანტი"),
    ("strategy", "Strategy Consultant", "სტრატეგიის კონსულტანტი"),
    ("management_consultant", "Management Consultant", "მართვის კონსულტანტი"),
    ("analyst", "Business Consultant", "ბიზნეს კონსულტანტი"),
)

# Extra labels the interview UI already sends (en + ka), besides the onboarding titles.
_EXTRA_ALIASES: dict[str, tuple[str, ...]] = {
    "frontend": ("Frontend Developer", "Frontend დეველოპერი"),
    "backend": ("Backend Developer", "Backend დეველოპერი"),
    "fullstack": ("Full Stack Developer", "Full Stack დეველოპერი"),
    "data_engineer": ("Data ინჟინერი",),
    "security": ("Security ინჟინერი",),
    "sre": ("SRE",),
    "account_executive": ("Sales Manager",),
}

# First match wins. Specific titles come before broad ones.
_MATCH_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"test automation|qa automation|sdet|ტესტირების ავტომატიზ", "qa_auto"),
    (r"\bqa\b|quality assurance|manual qa", "qa"),
    (r"engineering manager|ინჟინერიის მენეჯერ", "eng_manager"),
    (r"embedded|firmware|ჩაშენებულ", "embedded"),
    (r"game developer|game engineer|unity|unreal|თამაშების", "game"),
    (r"\bios\b|swiftui|\bswift\b", "ios"),
    (r"\bandroid\b|\bkotlin\b", "android"),
    (r"react native|flutter|mobile engineer|mobile developer|მობილური", "mobile"),
    (r"\breact\b|react\.js|reactjs", "react"),
    (r"full[\s-]?stack|ფულსტეკ", "fullstack"),
    (r"front[\s-]?end|ფრონტენდ|\bvue\b|\bangular\b", "frontend"),
    (r"back[\s-]?end|ბექენდ|django|fastapi|\bspring\b|node\.?js|\bpython\b|\bjava\b|\bgolang\b|\.net\b", "backend"),
    (r"web developer|ვებ დეველოპერ", "web"),
    (r"site reliability|\bsre\b", "sre"),
    (r"cloud engineer|cloud architect|cloud ინჟინერ", "cloud"),
    (r"system administrator|systems administrator|sysadmin|სისტემური ადმინ", "sysadmin"),
    (r"platform engineer|პლატფორმის ინჟინერ", "platform"),
    (r"security engineer|cybersecurity|infosec|უსაფრთხოების", "security"),
    (r"network engineer|ქსელის ინჟინერ", "network"),
    (r"\bdevops\b|kubernetes|terraform|ci/cd", "devops"),
    (r"data scientist|მონაცემთა მეცნიერ", "data_scientist"),
    (r"data engineer|მონაცემთა ინჟინერ", "data_engineer"),
    (r"machine learning|\bml engineer\b", "ml"),
    (r"\bai engineer\b|artificial intelligence", "ai"),
    (r"business intelligence|ბიზნეს ინტელექტ", "bi"),
    (r"data analyst|მონაცემთა ანალიტიკ", "data_analyst"),
    (r"product designer|პროდუქტის დიზაინერ", "product_designer"),
    (r"motion designer|motion design", "motion"),
    (r"graphic designer|გრაფიკული დიზაინერ", "graphic"),
    (r"\bux\b|user experience", "ux"),
    (r"\bui designer\b|user interface", "ui"),
    (r"product owner|პროდუქტის მფლობელ", "product_owner"),
    (r"product operations|პროდუქტის ოპერაცი", "product_ops"),
    (r"business analyst|ბიზნეს ანალიტიკოს", "business_analyst"),
    (r"product manager|პროდუქტის მენეჯერ", "product_manager"),
    (r"scrum master|\bscrum\b", "scrum"),
    (r"\bpmo\b", "pmo"),
    (r"program manager|პროგრამის მენეჯერ", "program_manager"),
    (r"project manager|პროექტის მენეჯერ", "project_manager"),
    (r"performance marketing|შედეგზე ორიენტირებული მარკეტინგ", "performance"),
    (r"content marketing|კონტენტ მარკეტინგ", "content_marketing"),
    (r"digital marketing|ციფრული მარკეტინგ", "digital_marketing"),
    (r"brand manager|ბრენდის მენეჯერ", "brand"),
    (r"\bseo\b", "seo"),
    (r"social media|სოციალური მედია", "social"),
    (r"customer success manager|მომხმარებლის წარმატების მენეჯერ", "customer_success"),
    (r"customer success associate|მომხმარებლის წარმატების სპეციალისტ", "success_associate"),
    (r"account executive|გაყიდვების მენეჯერ", "account_executive"),
    (r"account manager|ანგარიშის მენეჯერ", "account_manager"),
    (r"sales development|\bsdr\b|გაყიდვების განვითარ", "sdr"),
    (r"business development|\bbdr\b|ბიზნესის განვითარ", "bdr"),
    (r"financial analyst|ფინანსური ანალიტიკოს", "financial_analyst"),
    (r"bookkeeper|ბუღალტრული აღრიცხვ", "bookkeeper"),
    (r"financial controller|ფინანსური კონტროლერ|\bcontroller\b", "controller"),
    (r"\bauditor\b|აუდიტორ", "auditor"),
    (r"\baccountant\b|ბუღალტერ", "accountant"),
    (r"talent acquisition|ნიჭის მოძიებ", "talent"),
    (r"people operations", "people_ops"),
    (r"hr generalist|human resources|HR გენერალისტ", "hr_generalist"),
    (r"\brecruiter\b|რეკრუტერ", "recruiter"),
    (r"technical support|ტექნიკური მხარდაჭერ", "technical_support"),
    (r"support lead|მხარდაჭერის ხელმძღვანელ", "support_lead"),
    (r"customer support|support specialist|მხარდაჭერის სპეციალისტ", "support_specialist"),
    (r"executive assistant|აღმასრულებელი ასისტენტ", "executive_assistant"),
    (r"office manager|ოფისის მენეჯერ", "office_manager"),
    (r"operations manager|ოპერაციების მენეჯერ", "operations_manager"),
    (r"administrative assistant|ადმინისტრაციული ასისტენტ", "admin"),
    (r"medical assistant|სამედიცინო ასისტენტ", "medical_assistant"),
    (r"healthcare admin|ჯანდაცვის ადმინისტრატორ", "healthcare_admin"),
    (r"pharmacist|ფარმაცევტ", "pharmacist"),
    (r"\bphysician\b|\bdoctor\b|ექიმი", "physician"),
    (r"\bnurse\b|ექთან", "nurse"),
    (r"instructional designer|სასწავლო დიზაინერ", "instructional"),
    (r"academic coordinator|აკადემიური კოორდინატორ", "academic"),
    (r"\btutor\b|რეპეტიტორ", "tutor"),
    (r"\bteacher\b|მასწავლებელ", "teacher"),
    (r"electrician|ელექტრიკოს", "electrician"),
    (r"mechanical engineer|მექანიკოსი ინჟინერ", "mechanical"),
    (r"electrical engineer|ელექტრო ინჟინერ", "electrical"),
    (r"civil engineer|სამოქალაქო ინჟინერ", "civil"),
    (r"\btechnician\b|ტექნიკოს", "technician"),
    (r"copywriter|ქოფირაიტერ", "copywriter"),
    (r"journalist|ჟურნალისტ", "journalist"),
    (r"content writer|კონტენტის ავტორ", "content_writer"),
    (r"video producer|videographer|ვიდეო პროდიუსერ", "video"),
    (r"\beditor\b|რედაქტორ", "editor"),
    (r"legal counsel|იურიდიული მრჩეველ", "legal_counsel"),
    (r"paralegal|იურისტის ასისტენტ", "paralegal"),
    (r"compliance|შესაბამისობის", "compliance"),
    (r"\blawyer\b|\battorney\b|იურისტ", "lawyer"),
    (r"management consultant|მართვის კონსულტანტ", "management_consultant"),
    (r"strategy consultant|სტრატეგიის კონსულტანტ", "strategy"),
    (r"business consultant|ბიზნეს კონსულტანტ", "analyst"),
    (r"\bconsultant\b|კონსულტანტ", "consultant"),
)

_COMPILED_PATTERNS = tuple(
    (re.compile(pattern, re.IGNORECASE), slug) for pattern, slug in _MATCH_PATTERNS
)


def normalize_role_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").casefold()
    text = text.replace("-", " ").replace("/", " ").replace(".", " ")
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for slug, title, title_ka in INTERVIEW_ROLES:
        for label in (slug.replace("_", " "), title, title_ka, *_EXTRA_ALIASES.get(slug, ())):
            key = normalize_role_text(label)
            if key and key not in index:
                index[key] = slug
    return index


_ALIAS_INDEX = _alias_index()


def match_role_slug(text: str) -> str | None:
    """Map a job title or chosen role label to an onboarding role slug."""
    normalized = normalize_role_text(text)
    if not normalized:
        return None
    exact = _ALIAS_INDEX.get(normalized)
    if exact:
        return exact
    for pattern, slug in _COMPILED_PATTERNS:
        if pattern.search(text or ""):
            return slug
    return None
