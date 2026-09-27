from django.urls import path
from .views import UploadFirmwareAPIView, HistoryListAPIView  # 引入 API 視圖

urlpatterns = [
    path('upload/', UploadFirmwareAPIView.as_view(), name='upload_firmware'),
    path('history/', HistoryListAPIView.as_view(), name='upload_history'),
]
# 呼叫 UploadFirmwareAPIView 這個 class-based view 的 .as_view() 方法，轉換成 Django 可以處理的「view 函式」
# .as_view() 方法是用來處理 http 請求的