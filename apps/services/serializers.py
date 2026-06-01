from rest_framework import serializers

from apps.services.models import Service, ServiceField


class ServiceFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceField
        fields = ("id", "label", "key", "field_type", "required", "options", "sort_order")


class ServiceSerializer(serializers.ModelSerializer):
    fields = ServiceFieldSerializer(many=True, read_only=True)

    class Meta:
        model = Service
        fields = ("id", "name", "slug", "service_type", "description", "is_active", "config", "fields")
