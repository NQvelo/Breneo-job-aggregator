"""Load onboarding roles and their prepared questions into the database."""

from __future__ import annotations

from interview_api.constants import QUESTIONS_PER_ROLE
from interview_api.question_bank import ROLE_QUESTIONS
from interview_api.role_catalog import INTERVIEW_ROLES


def seed_role_questions(apps=None) -> None:
    """Upsert every onboarding role and its ten prepared questions."""
    if apps is None:
        from interview_api.models import InterviewRole, RoleQuestion
    else:
        InterviewRole = apps.get_model("interview_api", "InterviewRole")
        RoleQuestion = apps.get_model("interview_api", "RoleQuestion")

    catalog_slugs = [slug for slug, _title, _title_ka in INTERVIEW_ROLES]
    missing = [slug for slug in catalog_slugs if slug not in ROLE_QUESTIONS]
    extra = sorted(set(ROLE_QUESTIONS) - set(catalog_slugs))
    if missing or extra:
        raise RuntimeError(
            "Interview role catalog and question bank diverged. "
            f"Missing questions: {missing}. Extra banks: {extra}."
        )

    for slug, title, title_ka in INTERVIEW_ROLES:
        questions = ROLE_QUESTIONS[slug]
        if len(questions) != QUESTIONS_PER_ROLE or len(set(questions)) != QUESTIONS_PER_ROLE:
            raise RuntimeError(
                f"{slug} must have {QUESTIONS_PER_ROLE} unique prepared questions."
            )
        role, _created = InterviewRole.objects.update_or_create(
            slug=slug,
            defaults={"title": title, "title_ka": title_ka},
        )
        for position, question_text in enumerate(questions, start=1):
            RoleQuestion.objects.update_or_create(
                role=role,
                position=position,
                defaults={"question_text": question_text},
            )
