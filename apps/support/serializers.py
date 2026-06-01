from rest_framework import serializers

from apps.support.models import Ticket, TicketMessage


class TicketMessageSerializer(serializers.ModelSerializer):
    sender_email = serializers.EmailField(source="sender.email", read_only=True)

    class Meta:
        model = TicketMessage
        fields = ("id", "sender_email", "message", "is_staff_reply", "created_at")
        read_only_fields = ("id", "sender_email", "is_staff_reply", "created_at")


class TicketSerializer(serializers.ModelSerializer):
    messages = TicketMessageSerializer(many=True, read_only=True)
    initial_message = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Ticket
        fields = ("id", "subject", "status", "priority", "messages", "initial_message", "created_at", "updated_at")
        read_only_fields = ("id", "status", "messages", "created_at", "updated_at")

    def create(self, validated_data):
        initial_message = validated_data.pop("initial_message", "")
        ticket = Ticket.objects.create(user=self.context["request"].user, **validated_data)
        if initial_message:
            TicketMessage.objects.create(ticket=ticket, sender=self.context["request"].user, message=initial_message)
        return ticket
