# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class AuthGroup(models.Model):
    name = models.CharField(unique=True, max_length=150)

    class Meta:
        managed = False
        db_table = 'auth_group'


class AuthGroupPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)
    permission = models.ForeignKey('AuthPermission', models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_group_permissions'
        unique_together = (('group', 'permission'),)


class AuthPermission(models.Model):
    name = models.CharField(max_length=255)
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING)
    codename = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'auth_permission'
        unique_together = (('content_type', 'codename'),)


class AuthUser(models.Model):
    password = models.CharField(max_length=128)
    last_login = models.DateTimeField(blank=True, null=True)
    is_superuser = models.IntegerField()
    username = models.CharField(unique=True, max_length=150)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.CharField(max_length=254)
    is_staff = models.IntegerField()
    is_active = models.IntegerField()
    date_joined = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'auth_user'


class AuthUserGroups(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)
    group = models.ForeignKey(AuthGroup, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_user_groups'
        unique_together = (('user', 'group'),)


class AuthUserUserPermissions(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)
    permission = models.ForeignKey(AuthPermission, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'auth_user_user_permissions'
        unique_together = (('user', 'permission'),)


class Customer(models.Model):
    customer_id = models.CharField(primary_key=True, max_length=36)
    name = models.CharField(max_length=255)
    email = models.CharField(unique=True, max_length=255)
    customer_cert = models.TextField()
    manufacturer = models.ForeignKey('Manufacturer', models.DO_NOTHING)
    created_at = models.DateTimeField(blank=True, null=True)
    device_type = models.ForeignKey('Device', models.DO_NOTHING, db_column='device_type')

    class Meta:
        managed = False
        db_table = 'customer'


class Device(models.Model):
    device_type = models.CharField(primary_key=True, max_length=100)
    manufacturer = models.ForeignKey('Manufacturer', models.DO_NOTHING)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'device'


class DjangoAdminLog(models.Model):
    action_time = models.DateTimeField()
    object_id = models.TextField(blank=True, null=True)
    object_repr = models.CharField(max_length=200)
    action_flag = models.PositiveSmallIntegerField()
    change_message = models.TextField()
    content_type = models.ForeignKey('DjangoContentType', models.DO_NOTHING, blank=True, null=True)
    user = models.ForeignKey(AuthUser, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'django_admin_log'


class DjangoContentType(models.Model):
    app_label = models.CharField(max_length=100)
    model = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = 'django_content_type'
        unique_together = (('app_label', 'model'),)


class DjangoMigrations(models.Model):
    id = models.BigAutoField(primary_key=True)
    app = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    applied = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_migrations'


class DjangoSession(models.Model):
    session_key = models.CharField(primary_key=True, max_length=40)
    session_data = models.TextField()
    expire_date = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'django_session'


class Firmwaredownloadrequest(models.Model):
    id = models.BigAutoField(primary_key=True)
    customer = models.ForeignKey(Customer, models.DO_NOTHING)
    device_type = models.ForeignKey(Device, models.DO_NOTHING, db_column='device_type')
    firmware_version = models.CharField(max_length=50)
    manufacturer = models.ForeignKey('Manufacturer', models.DO_NOTHING)
    customer_signature_algorithm = models.CharField(max_length=50)
    customer_signature = models.TextField()
    request_status = models.CharField(max_length=8, blank=True, null=True)
    response_message = models.TextField(blank=True, null=True)
    download_url = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'firmwaredownloadrequest'


class Firmwaremetadata(models.Model):
    id = models.BigAutoField(primary_key=True)
    metadata_signature = models.CharField(max_length=512)
    metadata_signature_algorithm = models.CharField(max_length=255)
    metadata_digest_algorithm = models.CharField(max_length=255)
    firmware_signature = models.CharField(max_length=512)
    firmware_signature_algorithm = models.CharField(max_length=255)
    firmware_digest_algorithm = models.CharField(max_length=255)
    firmware_size = models.PositiveBigIntegerField()
    release_date = models.BigIntegerField()
    manufacturer = models.ForeignKey('Manufacturer', models.DO_NOTHING)
    device_type = models.ForeignKey(Device, models.DO_NOTHING, db_column='device_type')
    firmware_version = models.CharField(max_length=50)
    firmware_data = models.TextField()
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'firmwaremetadata'


class Manufacturer(models.Model):
    manufacturer_id = models.CharField(primary_key=True, max_length=36)
    manufacturer_name = models.CharField(max_length=255)
    email = models.CharField(unique=True, max_length=255)
    manufacturer_cert = models.TextField()
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'manufacturer'


class SubmitBlockRecord(models.Model):
    block_id = models.CharField(primary_key=True, max_length=32)
    tag = models.ForeignKey(Customer, models.DO_NOTHING, db_column='tag')
    metadata = models.ForeignKey(Firmwaremetadata, models.DO_NOTHING)
    data = models.TextField()
    created_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'submit_block_record'
