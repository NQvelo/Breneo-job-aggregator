"""Prepared technical questions, ten per onboarding role."""

from interview_api.question_bank.commercial import COMMERCIAL_QUESTIONS
from interview_api.question_bank.design_product import DESIGN_PRODUCT_QUESTIONS
from interview_api.question_bank.devops_data import DEVOPS_DATA_QUESTIONS
from interview_api.question_bank.software import SOFTWARE_QUESTIONS
from interview_api.question_bank.specialist import SPECIALIST_QUESTIONS

ROLE_QUESTIONS: dict[str, list[str]] = {}
for _group in (
    SOFTWARE_QUESTIONS,
    DEVOPS_DATA_QUESTIONS,
    DESIGN_PRODUCT_QUESTIONS,
    COMMERCIAL_QUESTIONS,
    SPECIALIST_QUESTIONS,
):
    overlap = set(ROLE_QUESTIONS) & set(_group)
    if overlap:
        raise RuntimeError(f"Duplicate interview roles in question bank: {sorted(overlap)}")
    ROLE_QUESTIONS.update(_group)
