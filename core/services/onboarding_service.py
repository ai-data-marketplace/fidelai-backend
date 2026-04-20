from django.db import transaction
from apps.users.models import RoleApplication, UserProfile, VerificationDocument, RoleApplicationStatusChoices

class OnboardingService:
    @staticmethod
    @transaction.atomic
    def complete_onboarding(user, profile_data, role_application_data, application_data, documents_files):
        """
        Completes the onboarding process for a user.
        Updates profile (creating it if missing), creates role application, and saves verification documents.
        """
        # 1. Update User Information (Full Name if provided)
        full_name = profile_data.get("full_name")
        if full_name:
            user.full_name = full_name
            user.save(update_fields=["full_name"])

        # 2. Update UserProfile (Create if not exists)
        profile, created = UserProfile.objects.get_or_create(user=user)
        
        profile.country = profile_data.get("country", profile.country)
        profile.native_language = profile_data.get("native_language", profile.native_language)
        profile.phone_number = profile_data.get("phone_number", profile.phone_number)
        
        profile_picture = profile_data.get("profile_picture")
        if profile_picture:
            profile.profile_picture = profile_picture
            
        profile.save()

        # 3. Create RoleApplication
        role_applied_for = role_application_data.get("role_applied_for")
        
        # We store the FULL payload (step_2 + step_3) in application_data JSON field
        role_app = RoleApplication.objects.create(
            user=user,
            role_applied_for=role_applied_for,
            application_data=application_data,
            status=RoleApplicationStatusChoices.PENDING
        )

        # 4. Save Verification Documents
        # documents_files is expected to be a list of UploadedFile objects
        for uploaded_file in documents_files:
            VerificationDocument.objects.create(
                user=user,
                role_application=role_app,
                file=uploaded_file,
                file_type=uploaded_file.content_type,
                purpose=f"Onboarding Document for {role_applied_for}"
            )

        return role_app
