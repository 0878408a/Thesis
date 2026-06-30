from django.db import models

'''
django.db：

Django 的資料庫模組，提供與資料庫互動的功能。
包括模型的定義、查詢集操作、遷移工具等。

models: 

是 Django 的模組，位於 django.db.models，它包含了一系列用於定義和操作資料模型的工具。

models.Model: 

是 Django 所有 models 的 Base Class，提供了模型和資料庫互動的核心功能。
當使用某個 class 繼承了 models.Model 時，Django 會將 class 映射為數據庫中的一張表，
並自動提供對資料庫的 CRUD 操作功能。

如: FirmwareMetadata 是一個繼承了 models.Model 的 class， 
metadata_signature 就是 FirmwareMetadata 的其中一個 attribute，
每個 attribute 都相當於資料庫中的一個 field，
這些 attribute 會被 Django 映射為資料庫中的一個 column。
'''

class Manufacturer(models.Model):
    manufacturer_id = models.CharField(primary_key=True, max_length=36)
    manufacturer_name = models.CharField(max_length=255)
    email = models.CharField(max_length=255, unique=True)
    manufacturer_cert = models.BinaryField()

    class Meta:
        db_table = 'manufacturer'
        managed = False  
        
        # 代表這個 Model 是用來對應資料庫中已存在的資料表，Django 不會幫你自動建立或修改這張表。

class Customer(models.Model): # tests.py測試用，views.py 沒用到
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

class Device(models.Model):
    device_type = models.CharField(max_length=100, primary_key=True)
    # 用 device_type 當「程式層的」主鍵，避免 Django 去 SELECT device.id
    manufacturer = models.ForeignKey(
        Manufacturer,
        on_delete=models.RESTRICT,
        # 刪除時若有外鍵關聯，就報錯
        db_column='manufacturer_id'
    )

    class Meta:
        db_table = 'device'
        unique_together = (('device_type', 'manufacturer'),)
        # 複合唯一鍵，每個廠商下的裝置型號不可重複
        managed = False


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
        # class Meta 是一個「內部類別（inner class）」，用來定設定與行為屬性。
        # 代表這個 Model 是用來對應資料庫中已存在的資料表，Django 不會幫你自動建立或修改這張表。
    
class SubmitBlockRecord(models.Model):
    #儲存上鏈資料
    object_id = models.CharField(max_length=66, primary_key=True)

    metadata_id = models.ForeignKey(
        'upload_firmware.FirmwareMetadata',
        on_delete=models.CASCADE,
        db_column='metadata_id',
        to_field='id'
    )

    submit_block_result = models.TextField()

    class Meta:
        db_table = 'submit_block_record'
        managed = False
