from __future__ import annotations

import logging

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from jobs.authentication.breneo_auth import BreneoJWTRequiredAuthentication

from .auth import resolve_user_id
from .exceptions import InterviewAPIError
from .models import InterviewQuestion
from .serializers import (
    InterviewEvaluationResponseSerializer,
    StartInterviewResponseSerializer,
    StartInterviewSerializer,
    SubmitAudioSerializer,
)
from .services.interview_service import InterviewService

logger = logging.getLogger(__name__)


class InterviewBaseView(APIView):
    authentication_classes = [BreneoJWTRequiredAuthentication]
    permission_classes = [IsAuthenticated]
    service_class = InterviewService

    def get_service(self) -> InterviewService:
        return self.service_class()


class StartInterviewView(InterviewBaseView):
    @extend_schema(
        request=StartInterviewSerializer,
        responses={201: StartInterviewResponseSerializer},
        tags=["Mock interview"],
    )
    def post(self, request):
        serializer = StartInterviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_id = resolve_user_id(request)
        if not user_id:
            return Response(
                {"detail": "Authenticated user could not be resolved."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            interview, question = self.get_service().start_interview(
                user_id=user_id,
                job_position=serializer.validated_data["job_position"],
            )
        except InterviewAPIError as exc:
            logger.warning("Start interview failed: %s", exc.message)
            return Response({"detail": exc.message}, status=exc.status_code)

        payload = {
            "interview": interview,
            "question": question,
        }
        return Response(StartInterviewResponseSerializer(payload).data, status=status.HTTP_201_CREATED)


class SubmitAudioView(InterviewBaseView):
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        request={"multipart/form-data": SubmitAudioSerializer},
        responses={200: InterviewEvaluationResponseSerializer},
        tags=["Mock interview"],
    )
    def post(self, request, question_id):
        serializer = SubmitAudioSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_id = resolve_user_id(request)
        if not user_id:
            return Response(
                {"detail": "Authenticated user could not be resolved."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        question = get_object_or_404(
            InterviewQuestion.objects.select_related("interview"),
            pk=question_id,
            interview__user_id=user_id,
        )

        uploaded_file = serializer.validated_data["uploaded_file"]

        try:
            evaluation = self.get_service().submit_audio(
                question=question,
                audio_file=uploaded_file,
            )
        except InterviewAPIError as exc:
            logger.warning("Submit audio failed for question %s: %s", question_id, exc.message)
            return Response({"detail": exc.message}, status=exc.status_code)
        except Exception:
            logger.exception("Unexpected error during audio submission for question %s", question_id)
            return Response(
                {"detail": "An unexpected error occurred while processing the interview answer."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            InterviewEvaluationResponseSerializer.from_evaluation(evaluation),
            status=status.HTTP_200_OK,
        )
