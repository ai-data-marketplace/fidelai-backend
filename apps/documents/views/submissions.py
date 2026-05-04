"""
Submission views for the documents app.

Endpoints
---------
POST   /api/v1/documents/submit/                 DocumentSubmitView
GET    /api/v1/documents/my-submissions/          MySubmissionsView
GET    /api/v1/documents/my-submissions/<uuid>/   MySubmissionDetailView
"""
from __future__ import annotations

import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.serializers import (
    DocumentSubmitSerializer,
    RawDocumentDetailSerializer,
    RawDocumentListSerializer,
)
from apps.documents.services.ingestion import DocumentIngestionHandlerService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------


class DocumentSubmitView(APIView):
    """
    Authenticated multipart endpoint for contributing Amharic documents.

    Accepts a file (PDF, DOCX, or TXT) plus metadata fields.  The file is
    stored immediately; all processing and validation are delegated to
    background workers so the response time is constant regardless of file size.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        request=DocumentSubmitSerializer,
        responses={
            201: RawDocumentListSerializer,
            400: OpenApiResponse(description="Validation error"),
        },
        summary="Submit a document for the AI dataset",
        tags=["Documents"],
    )
    def post(self, request, *args, **kwargs):
        serializer = DocumentSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            service = DocumentIngestionHandlerService()
            raw_document = service.handle(
                uploaded_file=serializer.validated_data["file"],
                user=request.user,
                metadata=serializer.validated_data,
            )
        except DjangoValidationError as exc:
            raise DRFValidationError(detail=exc.messages) from exc

        out = RawDocumentListSerializer(raw_document)
        return Response(out.data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# My Submissions — list
# ---------------------------------------------------------------------------


class MySubmissionsView(ListAPIView):
    """
    Returns a paginated list of all documents submitted by the authenticated
    contributor, ordered newest-first.  Documents belonging to other users are
    never returned — ownership is enforced at the queryset level.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = RawDocumentListSerializer

    @extend_schema(
        summary="List my document submissions",
        tags=["Documents"],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        # Guard for drf-spectacular schema generation (no real user available).
        if getattr(self, "swagger_fake_view", False):
            from apps.documents.models import RawDocument  # noqa: PLC0415
            return RawDocument.objects.none()
        return (
            request_user_documents(self.request.user)
            .order_by("-created_at")
        )


# ---------------------------------------------------------------------------
# My Submissions — detail
# ---------------------------------------------------------------------------


class MySubmissionDetailView(RetrieveAPIView):
    """
    Returns full detail (including nested files and validation notes) for a
    single document.  Only the owning contributor can retrieve their record.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = RawDocumentDetailSerializer

    @extend_schema(
        summary="Get detail of a single submission",
        tags=["Documents"],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        # Guard for drf-spectacular schema generation (no real user available).
        if getattr(self, "swagger_fake_view", False):
            from apps.documents.models import RawDocument  # noqa: PLC0415
            return RawDocument.objects.none()
        return request_user_documents(self.request.user).prefetch_related("files")


# ---------------------------------------------------------------------------
# Shared queryset helper
# ---------------------------------------------------------------------------


def request_user_documents(user):
    """Return RawDocument queryset scoped strictly to the given user."""
    from apps.documents.models import RawDocument  # noqa: PLC0415
    return RawDocument.objects.filter(user=user)
