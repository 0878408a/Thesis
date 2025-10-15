from django.urls import path
from .views import FirmwareDownloadRequestAPIView
from .views import download_firmware

urlpatterns = [
    path("request_download/", FirmwareDownloadRequestAPIView.as_view(), name="request_firmware_download"),
    path("download/<str:token>/", download_firmware, name="download_firmware"),
]
