from django.urls import path

from .views import StartInterviewView, SubmitAudioView

urlpatterns = [
    path("start/", StartInterviewView.as_view(), name="interview-start"),
    path(
        "submit-audio/<uuid:question_id>/",
        SubmitAudioView.as_view(),
        name="interview-submit-audio",
    ),
]
