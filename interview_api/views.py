from __future__ import annotations

import logging

from cloudinary.exceptions import BadRequest as CloudinaryBadRequest
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from jobs.authentication.breneo_auth import BreneoJWTRequiredAuthentication

from .authentication import InterviewBFFAuthentication

from .auth import resolve_user_id
from .exceptions import InterviewAPIError
from .models import InterviewQuestion
from .serializers import (
    StartInterviewResponseSerializer,
    StartInterviewSerializer,
    SubmitAudioSerializer,
    SubmitInterviewResponseSerializer,
    SubmitTextSerializer,
    TranscribeAudioSerializer,
)
from .services.interview_service import InterviewService
from .services.whisper_service import transcribe_audio

logger = logging.getLogger(__name__)


class InterviewBaseView(APIView):
    authentication_classes = [
        InterviewBFFAuthentication,
        BreneoJWTRequiredAuthentication,
    ]
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
                job_position=serializer.validated_data.get("job_position") or "",
                job=serializer.validated_data.get("job"),
                role_slug=serializer.validated_data.get("role") or "",
                spoken=serializer.validated_data.get("mode") != "text",
            )
        except InterviewAPIError as exc:
            logger.warning("Start interview failed: %s", exc.message)
            return Response({"detail": exc.message}, status=exc.status_code)

        payload = {
            "interview": interview,
            "question": question,
        }
        return Response(
            StartInterviewResponseSerializer(payload, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class SubmitAudioView(InterviewBaseView):
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        request={"multipart/form-data": SubmitAudioSerializer},
        responses={200: SubmitInterviewResponseSerializer},
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
            result = self.get_service().submit_audio(
                question=question,
                audio_file=uploaded_file,
            )
        except InterviewAPIError as exc:
            logger.warning("Submit audio failed for question %s: %s", question_id, exc.message)
            return Response({"detail": exc.message}, status=exc.status_code)
        except CloudinaryBadRequest as exc:
            logger.exception("Cloudinary rejected audio upload for question %s", question_id)
            return Response(
                {"detail": f"Audio upload failed: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.exception("Unexpected error during audio submission for question %s", question_id)
            return Response(
                {"detail": "An unexpected error occurred while processing the interview answer."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            SubmitInterviewResponseSerializer.from_submit_result(
                result,
                context={"request": request},
            ),
            status=status.HTTP_200_OK,
        )


class TranscribeAudioView(InterviewBaseView):
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        request={"multipart/form-data": TranscribeAudioSerializer},
        responses={200: {"type": "object", "properties": {"transcript": {"type": "string"}}}},
        tags=["Mock interview"],
    )
    def post(self, request):
        serializer = TranscribeAudioSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_id = resolve_user_id(request)
        if not user_id:
            return Response(
                {"detail": "Authenticated user could not be resolved."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            transcript = transcribe_audio(
                serializer.validated_data["uploaded_file"],
                language=serializer.validated_data.get("language") or "ka",
            )
        except InterviewAPIError as exc:
            logger.warning("Transcribe audio failed: %s", exc.message)
            return Response({"detail": exc.message}, status=exc.status_code)
        except Exception:
            logger.exception("Unexpected error during interview transcription")
            return Response(
                {"detail": "An unexpected error occurred while transcribing the recording."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({"transcript": transcript}, status=status.HTTP_200_OK)


class SubmitTextView(InterviewBaseView):
    @extend_schema(
        request=SubmitTextSerializer,
        responses={200: SubmitInterviewResponseSerializer},
        tags=["Mock interview"],
    )
    def post(self, request, question_id):
        serializer = SubmitTextSerializer(data=request.data)
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

        try:
            result = self.get_service().submit_text(
                question=question,
                answer=serializer.validated_data["answer"],
            )
        except InterviewAPIError as exc:
            logger.warning("Submit text failed for question %s: %s", question_id, exc.message)
            return Response({"detail": exc.message}, status=exc.status_code)
        except Exception:
            logger.exception("Unexpected error during text submission for question %s", question_id)
            return Response(
                {"detail": "An unexpected error occurred while reviewing the interview answer."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            SubmitInterviewResponseSerializer.from_submit_result(
                result,
                context={"request": request},
            ),
            status=status.HTTP_200_OK,
        )
