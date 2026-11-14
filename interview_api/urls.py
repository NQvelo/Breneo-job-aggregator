from django.urls import path

from .views import StartInterviewView, SubmitAudioView, SubmitTextView, TranscribeAudioView

urlpatterns = [
    path("start/", StartInterviewView.as_view(), name="interview-start"),
    path("transcribe/", TranscribeAudioView.as_view(), name="interview-transcribe"),
    path(
        "submit-audio/<uuid:question_id>/",
        SubmitAudioView.as_view(),
        name="interview-submit-audio",
    ),
    path(
        "submit-text/<uuid:question_id>/",
        SubmitTextView.as_view(),
        name="interview-submit-text",
    ),
]
