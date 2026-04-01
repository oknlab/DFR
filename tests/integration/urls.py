from django.http import JsonResponse
from django.urls import path


def ping(_request):
    return JsonResponse({"ping": "pong"})


urlpatterns = [
    path("ping/", ping, name="ping"),
]
