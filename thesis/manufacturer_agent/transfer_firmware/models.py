# transfer_firmware/models.py
from django.db import models

class Manufacturer(models.Model):
    manufacturer_id = models.CharField(primary_key=True, max_length=36)
    manufacturer_name = models.CharField(max_length=255)
    email = models.CharField(max_length=255, unique=True)
    manufacturer_cert = models.BinaryField()
    class Meta:
        db_table = 'manufacturer'
        managed = False

class Customer(models.Model):
    customer_id = models.CharField(
        primary_key=True,
        max_length=36
    )
    name = models.CharField(max_length=255)
    email = models.CharField(max_length=255)
    customer_cert = models.BinaryField()

    manufacturer = models.ForeignKey(
        Manufacturer,
        on_delete=models.CASCADE,
        db_column='manufacturer_id'
    )

    class Meta:
        db_table = 'customer'
        managed = False

# Device
# DB 是 composite PK
# Django 不支援
# ----------------------------
class Device(models.Model):
    device_type = models.CharField(
        max_length=100,
        primary_key=True  
    )

    manufacturer = models.ForeignKey(
        Manufacturer,
        on_delete=models.CASCADE,
        db_column='manufacturer_id'
    )

    class Meta:
        db_table = 'device'
        managed = False

class FirmwareMetadata(models.Model):
    id = models.BigAutoField(primary_key=True)
    metadata_signature = models.BinaryField()
    metadata_signature_algorithm = models.CharField(max_length=255)
    firmware_signature = models.BinaryField()
    firmware_signature_algorithm = models.CharField(max_length=255)
    firmware_size = models.PositiveBigIntegerField()
    release_date = models.BigIntegerField()
    manufacturer = models.ForeignKey(
        Manufacturer,
        on_delete=models.DO_NOTHING,
        db_column='manufacturer_id'
    )

    device_type = models.CharField(max_length=100)
    firmware_version = models.CharField(max_length=50, unique=True)
    firmware_data = models.BinaryField()
    class Meta:
        db_table = 'firmwaremetadata'
        managed = False
