from rest_framework import decorators, response, status, viewsets

from apps.support.models import Ticket, TicketMessage
from apps.support.serializers import TicketSerializer


class TicketViewSet(viewsets.ModelViewSet):
    serializer_class = TicketSerializer
    filterset_fields = ("status", "priority")

    def get_queryset(self):
        queryset = Ticket.objects.select_related("user").prefetch_related("messages")
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(user=self.request.user)

    @decorators.action(detail=True, methods=["post"])
    def reply(self, request, pk=None):
        ticket = self.get_object()
        message = request.data.get("message", "").strip()
        if not message:
            return response.Response({"message": "الرسالة مطلوبة."}, status=status.HTTP_400_BAD_REQUEST)
        TicketMessage.objects.create(ticket=ticket, sender=request.user, message=message, is_staff_reply=request.user.is_staff)
        return response.Response(self.get_serializer(ticket).data)
