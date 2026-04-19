from django.contrib import admin
from .models import CustomUser , EmailVerificationCode   , UserProfile , RoleApplication , VerificationDocument

admin.site.register(CustomUser)
admin.site.register(EmailVerificationCode)
admin.site.register(UserProfile)
admin.site.register(RoleApplication)
admin.site.register(VerificationDocument)