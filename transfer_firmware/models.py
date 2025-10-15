# transfer_firmware/models.py
from django.db import models

class SafeDeviceQuerySet(models.QuerySet):
    def _missing_manu(self, kwargs):
        # 有 device_type 但沒帶 manufacturer_id（或關聯寫法）就視為不安全(因為django orm 不支援雙主鍵的寫法，需要另外自訂檢查的邏輯)
        return (
            ('device_type' in kwargs)
            and not any(k in kwargs for k in ('manufacturer_id', 'manufacturer__manufacturer_id'))
        )

    def get(self, *args, **kwargs):
        if self._missing_manu(kwargs):
            raise ValueError("查 Device 時必須同時帶 manufacturer_id 與 device_type（或改用 Device.objects.for_type(...) 顯式跨廠商）。")
        return super().get(*args, **kwargs)

    def filter(self, *args, **kwargs):
        qs = super().filter(*args, **kwargs)
        # 標記這個查詢是用 device_type 單獨過濾的（可能危險）
        qs._unsafe_by_type_only = self._missing_manu(kwargs)
        return qs

    def first(self):
        # 阻擋「只用 device_type 然後 .first()」這種不安全寫法
        if getattr(self, '_unsafe_by_type_only', False):
            raise ValueError("不允許只用 device_type 就 .first()，請加上 manufacturer_id，或用 Device.objects.for_type(...) 顯式跨廠商。")
        return super().first()

    def update(self, **kwargs):
        if getattr(self, '_unsafe_by_type_only', False):
            raise ValueError("不允許只用 device_type 就做 update()。")
        return super().update(**kwargs)

    def delete(self):
        if getattr(self, '_unsafe_by_type_only', False):
            raise ValueError("不允許只用 device_type 就做 delete()。")
        return super().delete()

class DeviceManager(models.Manager.from_queryset(SafeDeviceQuerySet)):
    # 此類別使用django的自訂Manager功能，將內部方法傳入的參數，呼叫 SafeDeviceQuerySet 來處理。
    def by_key(self, manufacturer_id, device_type):
        # 建議大家都用這個方法來拿單筆
        return self.get(manufacturer_id=manufacturer_id, device_type=device_type)

    def for_type(self, device_type):
        # 跨廠商查詢：回傳所有符合 device_type 的裝置（不限制 manufacturer）
        return super().get_queryset().filter(device_type=device_type)

class Manufacturer(models.Model):
    manufacturer_id = models.CharField(primary_key=True, max_length=36)
    manufacturer_name = models.CharField(max_length=255)
    email = models.CharField(max_length=255, unique=True)
    manufacturer_cert = models.BinaryField()
    class Meta:
        db_table = 'manufacturer'
        managed = False

class Customer(models.Model):
    customer_id = models.CharField(primary_key=True, max_length=36)
    name = models.CharField(max_length=255)
    email = models.CharField(max_length=255, unique=True)
    customer_cert = models.BinaryField()
    class Meta:
        db_table = 'customer'
        managed = False

class Device(models.Model):
    device_type = models.CharField(max_length=100, primary_key=True)
    manufacturer = models.ForeignKey(
        Manufacturer, on_delete=models.RESTRICT, db_column='manufacturer_id'
    )
    
    objects = DeviceManager()  # 啟用安全 Manager
    
    class Meta:
        db_table = 'device'
        managed = False
        unique_together = (('device_type', 'manufacturer'),)

class FirmwareMetadata(models.Model):
    id = models.BigAutoField(primary_key=True)
    metadata_signature = models.BinaryField()
    metadata_signature_algorithm = models.CharField(max_length=255)
    firmware_signature = models.BinaryField()
    firmware_signature_algorithm = models.CharField(max_length=255)
    firmware_size = models.PositiveBigIntegerField()
    release_date = models.BigIntegerField()
    manufacturer_id = models.CharField(max_length=36) 
    device_type = models.CharField(max_length=100)
    firmware_version = models.CharField(max_length=50, unique=True)
    firmware_data = models.BinaryField()
    class Meta:
        db_table = 'firmwaremetadata'
        managed = False
