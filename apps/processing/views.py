from django.shortcuts import get_object_or_404

from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, extend_schema_view

from apps.processing.models import Chunk, TaskAssignment, TaskAssignmentStatusChoices
from apps.processing.serializers import (
	AnnotationCreateSerializer,
	AnnotationSubmitResponseSerializer,
	TaskAssignmentListSerializer,
	TaskChunkSerializer,
	TaskProgressSerializer,
)
from core.permissions import IsAssignmentOwner, IsAnnotator
from core.services import AnnotationExecutionService


class ProcessingPagination(PageNumberPagination):
	page_size = 20
	page_size_query_param = "page_size"
	max_page_size = 100


@extend_schema_view(
	get=extend_schema(
		responses={200: TaskAssignmentListSerializer(many=True)},
		description="List the authenticated annotator's assignments with progress metrics.",
	)
)
class MyAssignmentsListView(generics.ListAPIView):
	serializer_class = TaskAssignmentListSerializer
	permission_classes = [IsAnnotator]
	pagination_class = ProcessingPagination

	def get_queryset(self):
		status_filter = self.request.query_params.get("status")
		if status_filter and status_filter not in TaskAssignmentStatusChoices.values:
			from rest_framework.exceptions import ValidationError

			raise ValidationError({"detail": "Invalid assignment status filter."})

		return AnnotationExecutionService().get_my_assignments_queryset(self.request.user, status=status_filter)


class AcceptTaskAssignmentView(APIView):
	permission_classes = [IsAnnotator, IsAssignmentOwner]

	@extend_schema(
		request=None,
		responses={200: TaskAssignmentListSerializer},
		description="Accept an assignment owned by the authenticated annotator.",
	)
	def post(self, request, id):
		service = AnnotationExecutionService()
		assignment = service.get_assignment_for_user(id, request.user)
		self.check_object_permissions(request, assignment)
		assignment = service.accept_task_assignment(assignment)
		return Response(TaskAssignmentListSerializer(assignment).data, status=status.HTTP_200_OK)


class DeclineTaskAssignmentView(APIView):
	permission_classes = [IsAnnotator, IsAssignmentOwner]

	@extend_schema(
		request=None,
		responses={200: TaskAssignmentListSerializer},
		description="Decline an assignment owned by the authenticated annotator.",
	)
	def post(self, request, id):
		service = AnnotationExecutionService()
		assignment = service.get_assignment_for_user(id, request.user)
		self.check_object_permissions(request, assignment)
		assignment = service.decline_task_assignment(assignment)
		return Response(TaskAssignmentListSerializer(assignment).data, status=status.HTTP_200_OK)


class TaskAssignmentChunksView(APIView):
	permission_classes = [IsAnnotator, IsAssignmentOwner]

	@extend_schema(
		request=None,
		responses={200: TaskChunkSerializer(many=True)},
		description="Return the chunks for an accepted or in-progress assignment.",
	)
	def get(self, request, id):
		service = AnnotationExecutionService()
		assignment = service.get_assignment_for_user(id, request.user)
		self.check_object_permissions(request, assignment)
		chunks = service.get_assignment_chunks_queryset(assignment)
		return Response(TaskChunkSerializer(chunks, many=True).data, status=status.HTTP_200_OK)


class SubmitChunkAnnotationView(APIView):
	permission_classes = [IsAnnotator]

	@extend_schema(
		request=AnnotationCreateSerializer,
		responses={201: AnnotationSubmitResponseSerializer},
		description="Submit an annotation for a chunk that belongs to the annotator's accepted assignment.",
	)
	def post(self, request, chunk_id):
		chunk = get_object_or_404(Chunk.objects.select_related("extracted_document"), pk=chunk_id)
		serializer = AnnotationCreateSerializer(data=request.data, context={"request": request, "chunk": chunk})
		serializer.is_valid(raise_exception=True)

		service = AnnotationExecutionService()
		assignment = serializer.validated_data["task_assignment"]
		annotation, assignment = service.submit_chunk_annotation(
			assignment=assignment,
			chunk=chunk,
			annotator=request.user,
			validated_data={
				"domain_match": serializer.validated_data["domain_match"],
				"is_amharic": serializer.validated_data["is_amharic"],
				"readability": serializer.validated_data["readability"],
				"safety_label": serializer.validated_data["safety_label"],
				"confidence": serializer.validated_data["confidence"],
				"notes": serializer.validated_data.get("notes", ""),
				"time_spent_seconds": serializer.validated_data.get("time_spent_seconds"),
				"is_skipped": serializer.validated_data.get("is_skipped", False),
			},
		)

		progress = service.calculate_assignment_progress(assignment)
		return Response(
			{
				"message": "Annotation submitted successfully.",
				"annotation_id": annotation.id,
				"assignment_status": assignment.status,
				"progress": TaskProgressSerializer(progress).data,
			},
			status=status.HTTP_201_CREATED,
		)


class TaskAssignmentProgressView(APIView):
	permission_classes = [IsAnnotator, IsAssignmentOwner]

	@extend_schema(
		request=None,
		responses={200: TaskProgressSerializer},
		description="Return progress metrics for the authenticated annotator's assignment.",
	)
	def get(self, request, id):
		service = AnnotationExecutionService()
		assignment = service.get_assignment_for_user(id, request.user)
		self.check_object_permissions(request, assignment)
		progress = service.calculate_assignment_progress(assignment)
		return Response(TaskProgressSerializer(progress).data, status=status.HTTP_200_OK)
