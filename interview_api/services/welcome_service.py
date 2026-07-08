"""Georgian welcome message for interview session start."""

from __future__ import annotations

from interview_api.constants import MAX_INTERVIEW_QUESTIONS
from interview_api.services.job_context import InterviewJobContext


def build_welcome_text(context: InterviewJobContext) -> str:
    """Build a natural Georgian interviewer welcome for session start."""
    role = context.job_position.strip()
    question_count = MAX_INTERVIEW_QUESTIONS

    if context.company_name:
        intro = (
            f"გამარჯობა! მოგესალმებით {context.company_name}-ის სიმულაციურ ინტერვიუზე. "
            f"დღეს ერთად განვიხილავთ {role} პოზიციას."
        )
    else:
        intro = (
            "გამარჯობა! მოგესალმებით Breneo-ს მოკ ინტერვიუზე. "
            f"დღეს ერთად განვიხილავთ {role} პოზიციას."
        )

    body = (
        f"ინტერვიუს ფარგლებში მიიღებთ {question_count} კითხვას. "
        "თითოეულ კითხვაზე თავისუფლად მოგვიყევით ხმოვანი პასუხი — "
        "არ იჩქაროთ, დრო თქვენთვისაა. "
        "მზად ხართ? მაშინ დავიწყოთ პირველი კითხვა."
    )
    return f"{intro} {body}"
