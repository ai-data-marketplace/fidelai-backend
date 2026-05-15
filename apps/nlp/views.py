"""DRF views for the NLP annotation workflow API."""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.nlp.models import NLPChunk
from apps.nlp.permissions import NLPTaskOwnershipPermission
from apps.nlp.serializers import (
	NLPAnnotationCreateSerializer,
	NLPTaskAssignmentActionSerializer,
	NLPTaskDetailSerializer,
	NLPTaskListSerializer,
	NLPTaskProgressSerializer,
)
from apps.nlp.services import NLPAnnotationService


class NLPTaskPagination(PageNumberPagination):
	page_size = 10
	page_size_query_param = "page_size"
	max_page_size = 100


class NLPTaskListView(generics.ListAPIView):
	permission_classes = [IsAuthenticated]
	serializer_class = NLPTaskListSerializer
	pagination_class = NLPTaskPagination

	def get_queryset(self):
		return NLPAnnotationService().get_assigned_tasks_queryset(
			self.request.user,
			status_filter=self.request.query_params.get("status"),
		)


class NLPTaskDetailView(APIView):
	permission_classes = [IsAuthenticated, NLPTaskOwnershipPermission]

	@extend_schema(responses={200: NLPTaskDetailSerializer})
	def get(self, request, task_id):
		assignment = NLPAnnotationService().get_task_detail_assignment(task_id, request.user)
		self.check_object_permissions(request, assignment)
		serializer = NLPTaskDetailSerializer(assignment)
		return Response(serializer.data, status=status.HTTP_200_OK)


class NLPTaskProgressView(APIView):
	permission_classes = [IsAuthenticated, NLPTaskOwnershipPermission]

	@extend_schema(responses={200: NLPTaskProgressSerializer})
	def get(self, request, task_id):
		assignment = NLPAnnotationService().get_assignment_for_user(
			task_id,
			request.user,
			statuses=NLPAnnotationService.TASK_ACCESS_STATUSES,
		)
		self.check_object_permissions(request, assignment)
		progress = NLPAnnotationService().get_progress(assignment)
		return Response(NLPTaskProgressSerializer(progress).data, status=status.HTTP_200_OK)


class NLPTaskAcceptView(APIView):
	permission_classes = [IsAuthenticated, NLPTaskOwnershipPermission]

	@extend_schema(request=NLPTaskAssignmentActionSerializer, responses={200: NLPTaskListSerializer})
	def post(self, request, task_id):
		serializer = NLPTaskAssignmentActionSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)

		service = NLPAnnotationService()
		assignment = service.get_assignment_for_user(task_id, request.user, statuses=("assigned",))
		self.check_object_permissions(request, assignment)
		assignment = service.accept_assignment(assignment)
		return Response(NLPTaskListSerializer(assignment).data, status=status.HTTP_200_OK)


class NLPTaskDeclineView(APIView):
	permission_classes = [IsAuthenticated, NLPTaskOwnershipPermission]

	@extend_schema(request=NLPTaskAssignmentActionSerializer, responses={200: NLPTaskListSerializer})
	def post(self, request, task_id):
		serializer = NLPTaskAssignmentActionSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)

		service = NLPAnnotationService()
		assignment = service.get_assignment_for_user(
			task_id,
			request.user,
			statuses=("assigned", "accepted"),
		)
		self.check_object_permissions(request, assignment)
		assignment = service.decline_assignment(assignment)
		return Response(NLPTaskListSerializer(assignment).data, status=status.HTTP_200_OK)


class NLPChunkAnnotationCreateView(APIView):
	permission_classes = [IsAuthenticated, NLPTaskOwnershipPermission]

	@extend_schema(request=NLPAnnotationCreateSerializer)
	def post(self, request, chunk_id):
		chunk = get_object_or_404(NLPChunk.objects.select_related("source_chunk"), pk=chunk_id)
		self.check_object_permissions(request, chunk)

		# Pass the chunk into serializer context so task-specific validation
		# (e.g. sentiment label enforcement) can run inside the serializer.
		serializer = NLPAnnotationCreateSerializer(data=request.data, context={"chunk": chunk})
		serializer.is_valid(raise_exception=True)

		annotation = NLPAnnotationService().submit_annotation(
			user=request.user,
			chunk=chunk,
			validated_data=serializer.validated_data,
		)

		return Response(
			{
				"message": "Annotation submitted successfully.",
				"annotation_id": str(annotation.id),
				"chunk_id": str(chunk.id),
				"status": chunk.status,
			},
			status=status.HTTP_201_CREATED,
		)

