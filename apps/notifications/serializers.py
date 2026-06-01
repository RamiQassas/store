from rest_framework import serializers

from apps.notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ("id", "channel", "title", "body", "is_read", "metadata", "created_at")
        read_only_fields = ("id", "created_at")
