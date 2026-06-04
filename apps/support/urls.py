from django.urls import path
from . import views

urlpatterns = [
    path('chats/', views.chat_list, name='chat_list'),
    path('chats/create/', views.create_chat, name='create_chat'),
    path('chats/<uuid:room_id>/', views.chat_room, name='chat_room'),
    path('chats/<uuid:room_id>/close/', views.close_chat, name='close_chat'),
]
