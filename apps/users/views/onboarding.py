from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from drf_spectacular.utils import extend_schema

from apps.users.serializers.onboarding import (
    OnboardingSerializer, 
    OnboardingRequestBlueprintSerializer
)
from apps.users.models import RoleChoices, RoleApplication, RoleApplicationStatusChoices
from core.services.onboarding_service import OnboardingService

class OnboardingView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        request=OnboardingRequestBlueprintSerializer,
        responses={201: {"type": "object", "properties": {"message": {"type": "string"}, "application_status": {"type": "string"}}}}
    )
    def post(self, request):
        user = request.user

        # 1. Verification & Role Checks
        if not user.is_verified:
            return Response(
                {"message": "Email verification required before onboarding."},
                status=status.HTTP_403_FORBIDDEN
            )

        if user.role != RoleChoices.UNKNOWN:
            return Response(
                {"message": f"User already has a role assigned: {user.role}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. Check for pending applications
        has_pending = RoleApplication.objects.filter(
            user=user, 
            status=RoleApplicationStatusChoices.PENDING
        ).exists()
        
        if has_pending:
            return Response(
                {"message": "You already have a pending application."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3. Serialize and Validate
        serializer = OnboardingSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        # 4. Extract data and call Service
        profile_data = serializer.validated_data["profile"]
        role_app_data = serializer.validated_data["role_application"]
        application_data = serializer.validated_data["application_data"]
        
        # Add profile_picture to profile_data if it exists in FILES
        profile_picture = request.FILES.get("profile_picture")
        if profile_picture:
            profile_data["profile_picture"] = profile_picture

        documents = request.FILES.getlist("documents")

        try:
            OnboardingService.complete_onboarding(
                user=user,
                profile_data=profile_data,
                role_application_data=role_app_data,
                application_data=application_data,
                documents_files=documents
            )
            
            return Response(
                {
                    "message": "Application submitted successfully",
                    "application_status": "pending"
                },
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            return Response(
                {"message": f"An error occurred during onboarding: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
