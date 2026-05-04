from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination

from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.processing.serializers.expert_review_serializers import (
    ExpertTaskListSerializer,
    ExpertChunkTaskSerializer,
    ExpertReviewSubmissionSerializer,
)
from core.permissions import IsExpert
from core.services import ExpertReviewService

from drf_spectacular.utils import extend_schema, OpenApiExample

service = ExpertReviewService()

class ExpertTaskPagination(PageNumberPagination):
        page_size = 10
        page_size_query_param = "page_size"
        max_page_size = 100

class ExpertTaskListAPIView(generics.ListAPIView):
    permission_classes = [IsExpert]
    serializer_class = ExpertTaskListSerializer

 
    pagination_class = ExpertTaskPagination

    def get_queryset(self):
        return service.get_my_assignments_queryset(self.request.user)


class ExpertTaskAcceptAPIView(APIView):
    permission_classes = [IsExpert]

    @extend_schema(request=None, description="Accept an expert assignment (no request body).")
    def post(self, request, id):
        try:
            assignment = service.get_assignment_for_user(id, request.user)
            service.accept_assignment(assignment)
            return Response({"detail": "Accepted"}, status=status.HTTP_200_OK)
        except PermissionDenied as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ValidationError as exc:
            return Response({"detail": exc.detail if hasattr(exc, 'detail') else str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class ExpertTaskDeclineAPIView(APIView):
    permission_classes = [IsExpert]

    @extend_schema(request=None, description="Decline an expert assignment (no request body).")
    def post(self, request, id):
        try:
            assignment = service.get_assignment_for_user(id, request.user)
            service.decline_assignment(assignment)
            return Response({"detail": "Declined"}, status=status.HTTP_200_OK)
        except PermissionDenied as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ValidationError as exc:
            return Response({"detail": exc.detail if hasattr(exc, 'detail') else str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class ExpertTaskChunksAPIView(APIView):
    permission_classes = [IsExpert]

    def get(self, request, id):
        try:
            assignment = service.get_assignment_for_user(id, request.user)
            task_chunks = service.get_task_chunks(assignment)
            serializer = ExpertChunkTaskSerializer(task_chunks["chunks"], many=True, context={"request": request})
            task = task_chunks["task"]
            return Response({"task_id": task.id, "name": task.name, "domain": task.domain, "task_chunks": serializer.data})
        except PermissionDenied as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ValidationError as exc:
            return Response({"detail": exc.detail if hasattr(exc, 'detail') else str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class ExpertChunkResolveAPIView(APIView):
    permission_classes = [IsExpert]
    @extend_schema(
        request=ExpertReviewSubmissionSerializer,
        examples=[
            OpenApiExample(
                "Resolve example",
                value={
                    "domain_match": "match",
                    "is_amharic": True,
                    "readability": "high",
                    "safety_label": "safe",
                    "confidence": "high",
                    "notes": "Text is relevant and high quality.",
                    "resolution_reasoning": "Consensus ambiguous; expert confirms domain and approves.",
                    "final_decision": "approved",
                },
                request_only=True,
                description="Example payload for resolving an expert chunk",
            )
        ],
        description="Submit an expert resolution for a chunk.",
    )
    def post(self, request, chunk_id):
        serializer = ExpertReviewSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = service.resolve_chunk(chunk_id, request.user, serializer.validated_data)
            return Response(result, status=status.HTTP_200_OK)
        except PermissionDenied as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ValidationError as exc:
            return Response({"detail": exc.detail if hasattr(exc, 'detail') else str(exc)}, status=status.HTTP_400_BAD_REQUEST)
