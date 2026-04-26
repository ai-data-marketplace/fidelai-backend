from django.apps import apps
from django.contrib import admin
from django.contrib.admin.sites import AlreadyRegistered


for model in apps.get_app_config("documents").get_models():
	if model._meta.abstract:
		continue

	try:
		admin.site.register(model)
	except AlreadyRegistered:
		continue
