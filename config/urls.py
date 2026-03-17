from django.http import HttpRequest
from django.shortcuts import render
from django.urls import path

from config.api import api


def test_ui_view(request: HttpRequest):
    return render(request, "test_ui.html")


urlpatterns = [
    path("api/", api.urls),
    path("test-ui/", test_ui_view),
]
