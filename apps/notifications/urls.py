from django.urls import path

from apps.notifications.views import (
	MarkAllNotificationsReadView,
	MarkNotificationReadView,
	NotificationListView,
	UnreadCountView,
)

urlpatterns = [
	path("", NotificationListView.as_view(), name="notifications"),
	path("<uuid:pk>/read/", MarkNotificationReadView.as_view(), name="notification-read"),
	path("read-all/", MarkAllNotificationsReadView.as_view(), name="notification-read-all"),
	path("unread-count/", UnreadCountView.as_view(), name="notification-unread-count"),
]
