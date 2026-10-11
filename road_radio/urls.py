from django.urls import path

from . import views

urlpatterns = [
    path("config/", views.config),
    path("profile/", views.profile),
    path("directory/", views.directory),
    path("colleagues/", views.colleagues),
    path("channel-access/", views.channel_access),
    path("contacts/", views.contacts),
    path("contacts/requests/", views.contact_requests),
    path("contacts/requests/<int:request_id>/respond/", views.respond_contact),
    path("contacts/<int:user_id>/", views.remove_contact),
    path("blocks/", views.blocks),
    path("blocks/<int:user_id>/", views.unblock),
    path("calls/", views.calls),
    path("calls/<uuid:call_id>/respond/", views.respond_call),
    path("calls/<uuid:call_id>/end/", views.end_call),
]
