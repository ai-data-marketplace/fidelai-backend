import json
from rest_framework import serializers
from apps.users.models import RoleChoices


# --- Documentation Serializers (for Redoc/Swagger) ---

class OnboardingProfileSchemaSerializer(serializers.Serializer):
    full_name = serializers.CharField(required=False)
    phone_number = serializers.CharField(required=False)
    country = serializers.CharField(required=True)
    native_language = serializers.CharField(required=True)


class OnboardingRoleAppSchemaSerializer(serializers.Serializer):
    role_applied_for = serializers.ChoiceField(choices=RoleChoices.choices)


class OnboardingDataSchemaSerializer(serializers.Serializer):
    step_2 = serializers.DictField(
        help_text="Role-specific data (agreements for contributors, quiz scores for annotators, etc.)"
    )
    step_3 = serializers.DictField(
        help_text="Readiness check results"
    )


class OnboardingRequestBlueprintSerializer(serializers.Serializer):
    """
    Blueprint serializer used solely for drf-spectacular documentation.
    Shows the nested structure of the multipart/form-data payload.
    """
    profile = OnboardingProfileSchemaSerializer()
    role_application = OnboardingRoleAppSchemaSerializer()
    application_data = OnboardingDataSchemaSerializer()
    profile_picture = serializers.FileField(required=False)
    documents = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        help_text="Multiple files for verification (Required for Expert role)"
    )


class OnboardingSerializer(serializers.Serializer):
    # These fields will be passed as JSON strings in multipart/form-data
    profile = serializers.JSONField(
        required=True, 
        help_text="JSON string of OnboardingProfileSchemaSerializer"
    )
    role_application = serializers.JSONField(
        required=True, 
        help_text="JSON string of OnboardingRoleAppSchemaSerializer"
    )
    application_data = serializers.JSONField(
        required=True, 
        help_text="JSON string of OnboardingDataSchemaSerializer"
    )

    def validate_profile(self, value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise serializers.ValidationError("Invalid JSON format for profile.")
        
        required_fields = ["country", "native_language"]
        for field in required_fields:
            if not value.get(field):
                raise serializers.ValidationError(f"Profile: {field} is required.")
        return value

    def validate_role_application(self, value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise serializers.ValidationError("Invalid JSON format for role_application.")
        
        if not value.get("role_applied_for"):
            raise serializers.ValidationError("Role applied for is required.")
        
        role = value.get("role_applied_for")
        if role not in [RoleChoices.CONTRIBUTOR, RoleChoices.ANNOTATOR, RoleChoices.EXPERT, RoleChoices.BUYER]:
            raise serializers.ValidationError(f"Invalid role: {role}")
            
        return value

    def validate_application_data(self, value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise serializers.ValidationError("Invalid JSON format for application_data.")
        
        step_2 = value.get("step_2")
        step_3 = value.get("step_3")
        
        if not step_2 or not step_3:
            raise serializers.ValidationError("Both step_2 and step_3 data are required in application_data.")
            
        # Global Step 3: Readiness Check is required for everyone
        readiness = step_3.get("readiness_check")
        if not readiness or "answers" not in readiness or "score" not in readiness:
            raise serializers.ValidationError("application_data.step_3: readiness_check with answers and score is required.")

        return value

    def validate(self, data):
        role = data["role_application"]["role_applied_for"]
        app_data = data["application_data"]
        step_2 = app_data.get("step_2", {})
        
        # 1. Contributor Validation
        if role == RoleChoices.CONTRIBUTOR:
            agreements = step_2.get("agreements", {})
            required_agreements = [
                "ownership_confirmed", "no_copyright_content", 
                "no_pii", "liability_acceptance", "dataset_usage_consent"
            ]
            for agreement in required_agreements:
                if not agreements.get(agreement):
                    raise serializers.ValidationError(f"Contributor: {agreement.replace('_', ' ')} must be confirmed.")

        # 2. Annotator Validation
        elif role == RoleChoices.ANNOTATOR:
            required_fields = ["amharic_quiz_score", "annotation_test_score", "availability_hours_per_week", "preferred_domains"]
            for field in required_fields:
                if field not in step_2:
                    raise serializers.ValidationError(f"Annotator: {field.replace('_', ' ')} is required.")

        # 3. Expert Validation
        elif role == RoleChoices.EXPERT:
            required_fields = ["institution", "years_of_experience", "domain_specialization"]
            for field in required_fields:
                if field not in step_2:
                    raise serializers.ValidationError(f"Expert: {field.replace('_', ' ')} is required.")
            
            # Documents check
            documents = self.context.get("request").FILES.getlist("documents")
            if not documents:
                raise serializers.ValidationError("Expert: At least one verification document is required.")

        # 4. Buyer Validation
        elif role == RoleChoices.BUYER:
            required_fields = ["organization_name", "industry", "use_case"]
            for field in required_fields:
                if field not in step_2:
                    raise serializers.ValidationError(f"Buyer: {field.replace('_', ' ')} is required.")

        return data
