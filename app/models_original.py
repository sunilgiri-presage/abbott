from sre_constants import MAX_UNTIL
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
# from phonenumber_field.modelfields import PhoneNumberField
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from rest_framework.authtoken.models import Token
from django.contrib.postgres.fields import ArrayField


# Create your models here.
class CompanyMaster(models.Model):
    comp_name = models.CharField(max_length=150)
    contact_number = models.CharField(max_length=15)
    company_description = models.TextField()
    creation_date=models.DateField(auto_now=True)
    comp_id_cmms = models.CharField(max_length=150, unique=True, null=True, default="619be26f5571c904ef4fa59b")

    class Meta:
        db_table = 'company_master'
        ordering = ['creation_date']
        # managed = False

class LocationMaster(models.Model):
    # company = models.ForeignKey(CompanyMaster, related_name='locations', on_delete=models.CASCADE)
    location_name = models.CharField(max_length=150)
    location = models.CharField(max_length=15)
    address = models.TextField()
    location_description = models.TextField()
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster, related_name='location_org', on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)

    class Meta:
        db_table = 'location_master'
        # managed = False

class AreaMaster(models.Model):
    location = models.ForeignKey(LocationMaster,on_delete=models.CASCADE)
    area_name = models.CharField(max_length=150)
    area_type = models.CharField(max_length=15)
    area_description = models.TextField()
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)

    class Meta:
        db_table = 'area_master'
        # managed = False

class EquipmentMaster(models.Model):
    area = models.ForeignKey(AreaMaster,on_delete=models.CASCADE)
    equipment_name = models.CharField(max_length=150)
    equipment_type = models.CharField(max_length=15)
    equipment_class = models.CharField(max_length=15)
    equipment_description = models.TextField()
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)

    class Meta:
        db_table = 'equipment_master'
        # managed = False  

class AssetMaster(models.Model):
    equipment = models.ForeignKey(EquipmentMaster,on_delete=models.CASCADE)
    asset_name = models.CharField(max_length=150)
    asset_type = models.CharField(max_length=15)
    asset_class_type = models.CharField(max_length=15)
    asset_description = models.TextField()
    # asset_make = models.CharField(max_length=150)
    # asset_model = models.CharField(max_length=150)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)

    class Meta:
        db_table = 'asset_master'
        # managed = False

class AssetImage(models.Model):
    asset = models.ForeignKey(AssetMaster,on_delete=models.CASCADE)
    file = models.FileField(blank=True, null=True)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)

    class Meta:
        db_table = 'asset_image'
        # managed = False  

# need change
class DeviceModelMaster(models.Model):
    device_key = models.CharField(max_length=150, primary_key=True)
    device_value = models.CharField(max_length=150)
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE, default=26)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    creation_date=models.DateField(auto_now=True)

    class Meta:
        db_table = 'device_model_master'
        # managed = False 

class DeviceMountMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    # endpoint_name = models.CharField(max_length=150)
    mount_location = models.CharField(max_length=50)
    mount_type = models.CharField(max_length=50)
    mount_material = models.CharField(max_length=50)
    mount_direction = models.CharField(max_length=50)
    creation_date=models.DateField(auto_now=True)

    class Meta:
        db_table = 'device_mount_master'
        # managed = False 

class RoleMaster(models.Model):
    name = models.CharField(max_length=50)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'role_master'
        # managed = False  


class MyAccountManager(BaseUserManager):
    def create_user(self, email, username, password=None):
        if not email:
            raise ValueError('Users must have an email address')
        if not username:
            raise ValueError('Users must have a username')

        user = self.model(
            email=self.normalize_email(email),
            username=username,
        )

        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, username, password):
        user = self.create_user(
            email=self.normalize_email(email),
            password=password,
            username=username,
        )
        user.is_admin = True
        user.is_staff = True
        user.is_superuser = True
        user.save(using=self._db)
        return user


class Account(AbstractBaseUser):
    email = models.EmailField(verbose_name="email", max_length=60, unique=True)
    username = models.CharField(max_length=30, unique=True)
    date_joined = models.DateTimeField(verbose_name='date joined', auto_now_add=True)
    last_login = models.DateTimeField(verbose_name='last login', auto_now=True)
    is_admin = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)


    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    objects = MyAccountManager()

    def __str__(self):
        return self.email

    # For checking permissions. to keep it simple all admin have ALL permissons
    def has_perm(self, perm, obj=None):
        return self.is_admin

    # Does this user have permission to view this app? (ALWAYS YES FOR SIMPLICITY)
    def has_module_perms(self, app_label):
        return True
        
    class Meta:
        db_table = 'account'
        # managed = False 

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_auth_token(sender, instance=None, created=False, **kwargs):
    if created:
        Token.objects.create(user=instance)

class Admin(models.Model):
    user = models.OneToOneField(Account,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)
    
    class Meta:
        db_table = 'admin'

class Customer(models.Model):
    user = models.OneToOneField(Account,on_delete=models.CASCADE)
    # first_name = models.CharField(max_length=50)
    # last_name = models.CharField(max_length=50)
    # phone = PhoneNumberField(null=False, blank=False)
    role = models.ForeignKey(RoleMaster,on_delete=models.CASCADE)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)

    class Meta:
        db_table = 'customers'

class RawDataMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    fs = models.IntegerField()
    no_of_samples = models.IntegerField( null=True, blank=True)
    raw_data = ArrayField(models.CharField(max_length=50000))
    axis = models.CharField(max_length=10)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'raw_data_master'
        # managed = False

class AccelerationAmplitudeMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    fs = models.IntegerField()
    no_of_samples = models.IntegerField( null=True, blank=True)
    data = ArrayField(models.CharField(max_length=50000)) 
    axis = models.CharField(max_length=10)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'acceleration_amplitude_master'
        # managed = False

class AccelerationFrequencyMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    fs = models.IntegerField()
    no_of_samples = models.IntegerField( null=True, blank=True)
    data = ArrayField(models.CharField(max_length=50000))
    axis = models.CharField(max_length=10)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'acceleration_frequency_master'
        # managed = False

class VelocityAmplitudeMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    fs = models.IntegerField()
    no_of_samples = models.IntegerField( null=True, blank=True)
    data = ArrayField(models.CharField(max_length=50000)) 
    axis = models.CharField(max_length=10)
    velocity_rms = models.DecimalField(max_digits=20, decimal_places=2)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'velocity_amplitude_master'
        # managed = False

class VelocityFrequencyMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    fs = models.IntegerField()
    no_of_samples = models.IntegerField( null=True, blank=True)
    data = ArrayField(models.CharField(max_length=50000))
    axis = models.CharField(max_length=10)
    velocity_rms = models.DecimalField(max_digits=20, decimal_places=2)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'velocity_frequency_master'
        # managed = False

class DisplacementAmplitudeMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    fs = models.IntegerField()
    no_of_samples = models.IntegerField( null=True, blank=True)
    data = ArrayField(models.CharField(max_length=50000))
    axis = models.CharField(max_length=10)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'displacement_amplitude_master'
        # managed = False

class DisplacementFrequencyMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    fs = models.IntegerField()
    no_of_samples = models.IntegerField( null=True, blank=True)
    data = ArrayField(models.CharField(max_length=50000))
    axis = models.CharField(max_length=10)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'displacement_frequency_master'
        # managed = False


class VelocityStatTimeMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    rms = models.DecimalField(max_digits=20, decimal_places=2)
    axis = models.CharField(max_length=10)
    peak = models.DecimalField(max_digits=20, decimal_places=2)
    peak_to_peak = models.DecimalField(max_digits=20, decimal_places=2)
    kurtosis = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    flag = models.BooleanField(default=False)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'velocity_stat_time_master'
        # managed = False

# class VelocityStatFreqMaster(models.Model):
#     device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
#     timestamp = models.DateTimeField()
#     rms = models.DecimalField(max_digits=20, decimal_places=2)
#     axis = models.CharField(max_length=10)
#     peak = models.DecimalField(max_digits=20, decimal_places=2)
#     peak_to_peak = models.DecimalField(max_digits=20, decimal_places=2)
#     kurtosis = models.DecimalField(max_digits=20, decimal_places=2, default=0)
#     org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
#     creation_date=models.DateField(auto_now=True)
#     class Meta:
#         db_table = 'velocity_stat_freq_master'

class ISOFlagsMaster(models.Model):
    min_range_inch = models.DecimalField(max_digits=20, decimal_places=2)
    max_range_inch = models.DecimalField(max_digits=20, decimal_places=2)
    min_range_mm = models.DecimalField(max_digits=20, decimal_places=2)
    max_range_mm = models.DecimalField(max_digits=20, decimal_places=2)
    flag = models.CharField(max_length=30)
    class_type = models.CharField(max_length=100)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'iso_flags_master'
        # managed = False

class DeviceHealthStatus(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    data = models.DecimalField(max_digits=20, decimal_places=2)
    axis = models.CharField(max_length=10)
    flag = models.CharField(max_length=30)
    device_score = models.DecimalField(max_digits=20, decimal_places=2)
    class_type = models.CharField(max_length=100)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'device_health_status'
        # managed = False

class TimeWaveMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    data = ArrayField(models.CharField(max_length=50000), null=True, blank=True)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'time_wave_master'
        # managed = False

class FrequencyWaveMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    data = ArrayField(models.CharField(max_length=50000), null=True, blank=True)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'frequency_wave_master'
        # managed = False

class AccelerationHarmonicsMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    axis = models.CharField(max_length=10)
    phase = models.DecimalField(max_digits=20, decimal_places=2)
    one_amp = models.DecimalField(max_digits=20, decimal_places=5)
    one_freq = models.DecimalField(max_digits=20, decimal_places=5)
    two_amp = models.DecimalField(max_digits=20, decimal_places=5)
    two_freq = models.DecimalField(max_digits=20, decimal_places=5)
    three_amp = models.DecimalField(max_digits=20, decimal_places=5)
    three_freq = models.DecimalField(max_digits=20, decimal_places=5)
    four_amp = models.DecimalField(max_digits=20, decimal_places=5)
    four_freq = models.DecimalField(max_digits=20, decimal_places=5)
    five_amp = models.DecimalField(max_digits=20, decimal_places=5)
    five_freq = models.DecimalField(max_digits=20, decimal_places=5)
    six_amp = models.DecimalField(max_digits=20, decimal_places=5)
    six_freq = models.DecimalField(max_digits=20, decimal_places=5)
    seven_amp = models.DecimalField(max_digits=20, decimal_places=5)
    seven_freq = models.DecimalField(max_digits=20, decimal_places=5)
    eight_amp = models.DecimalField(max_digits=20, decimal_places=5)
    eight_freq = models.DecimalField(max_digits=20, decimal_places=5)
    nine_amp = models.DecimalField(max_digits=20, decimal_places=5)
    nine_freq = models.DecimalField(max_digits=20, decimal_places=5)
    ten_amp = models.DecimalField(max_digits=20, decimal_places=5)
    ten_freq = models.DecimalField(max_digits=20, decimal_places=5)
    flag = models.BooleanField(default=False)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'acceleration_harmonics_master'
        # managed = False

class VelocityHarmonicsMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    axis = models.CharField(max_length=10)
    phase = models.DecimalField(max_digits=20, decimal_places=2)
    one_amp = models.DecimalField(max_digits=20, decimal_places=5)
    one_freq = models.DecimalField(max_digits=20, decimal_places=5)
    two_amp = models.DecimalField(max_digits=20, decimal_places=5)
    two_freq = models.DecimalField(max_digits=20, decimal_places=5)
    three_amp = models.DecimalField(max_digits=20, decimal_places=5)
    three_freq = models.DecimalField(max_digits=20, decimal_places=5)
    four_amp = models.DecimalField(max_digits=20, decimal_places=5)
    four_freq = models.DecimalField(max_digits=20, decimal_places=5)
    five_amp = models.DecimalField(max_digits=20, decimal_places=5)
    five_freq = models.DecimalField(max_digits=20, decimal_places=5)
    six_amp = models.DecimalField(max_digits=20, decimal_places=5)
    six_freq = models.DecimalField(max_digits=20, decimal_places=5)
    seven_amp = models.DecimalField(max_digits=20, decimal_places=5)
    seven_freq = models.DecimalField(max_digits=20, decimal_places=5)
    eight_amp = models.DecimalField(max_digits=20, decimal_places=5)
    eight_freq = models.DecimalField(max_digits=20, decimal_places=5)
    nine_amp = models.DecimalField(max_digits=20, decimal_places=5)
    nine_freq = models.DecimalField(max_digits=20, decimal_places=5)
    ten_amp = models.DecimalField(max_digits=20, decimal_places=5)
    ten_freq = models.DecimalField(max_digits=20, decimal_places=5)
    flag = models.BooleanField(default=False)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'velocity_harmonics_master'
        # managed = False

class DisplacementHarmonicsMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    axis = models.CharField(max_length=10)
    phase = models.DecimalField(max_digits=20, decimal_places=2)
    one_amp = models.DecimalField(max_digits=20, decimal_places=5)
    one_freq = models.DecimalField(max_digits=20, decimal_places=5)
    two_amp = models.DecimalField(max_digits=20, decimal_places=5)
    two_freq = models.DecimalField(max_digits=20, decimal_places=5)
    three_amp = models.DecimalField(max_digits=20, decimal_places=5)
    three_freq = models.DecimalField(max_digits=20, decimal_places=5)
    four_amp = models.DecimalField(max_digits=20, decimal_places=5)
    four_freq = models.DecimalField(max_digits=20, decimal_places=5)
    five_amp = models.DecimalField(max_digits=20, decimal_places=5)
    five_freq = models.DecimalField(max_digits=20, decimal_places=5)
    six_amp = models.DecimalField(max_digits=20, decimal_places=5)
    six_freq = models.DecimalField(max_digits=20, decimal_places=5)
    seven_amp = models.DecimalField(max_digits=20, decimal_places=5)
    seven_freq = models.DecimalField(max_digits=20, decimal_places=5)
    eight_amp = models.DecimalField(max_digits=20, decimal_places=5)
    eight_freq = models.DecimalField(max_digits=20, decimal_places=5)
    nine_amp = models.DecimalField(max_digits=20, decimal_places=5)
    nine_freq = models.DecimalField(max_digits=20, decimal_places=5)
    ten_amp = models.DecimalField(max_digits=20, decimal_places=5)
    ten_freq = models.DecimalField(max_digits=20, decimal_places=5)
    flag = models.BooleanField(default=False)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'displacement_harmonics_master'
        # managed = False

class HardwareMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    hardware_type = models.CharField(max_length=15, default=None, null=True, blank=True)
    hardware_components = ArrayField(models.CharField(max_length=50), default=None, null=True, blank=True)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)

    class Meta:
        db_table = 'hardware_master'
        # managed = False

class FirmwareMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    firmware_version = models.CharField(max_length=15, null=True, blank=True)
    no_of_samples = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    no_of_files = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    upload_time = models.CharField(max_length=10, null=True, blank=True)
    sleep_time = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    machine_running = models.CharField(max_length=10, null=True, blank=True)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)

    class Meta:
        db_table = 'firmware_master'
        # managed = False

class SignalProcessingMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    vibration_rms = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    overall_rms = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    vibration_twf = models.CharField(max_length=15, null=True, blank=True)
    vib_fcutoff = models.CharField(max_length=15, null=True, blank=True)
    vib_sampling_rate = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    vib_fmax = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    vib_no_of_samples = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    vib_freq_resolution = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    freq_spec_waterfall = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    acc_fcutoff = models.CharField(max_length=15, null=True, blank=True)
    acc_sampling_rate = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    acc_fmax = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    acc_no_of_samples = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    acc_freq_resolution = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    acc_rms = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    temperature = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    battery_cut_off = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    battery_unstable_current = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    battery_unstable_samples = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    battery_max_cycle = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    rul_power_coeff = models.CharField(max_length=15, null=True, blank=True)
    rul_bound_limit = models.CharField(max_length=15, null=True, blank=True)
    rul_ffa_rpm = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    rul_ffa_ffr = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    rul_ffa_max_har_count = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    rul_ffa_min_accp_rpm = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    rul_ffa_max_accp_rpm = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    rul_learning_cond = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    sensitivity = models.IntegerField(default=8,null=True, blank=True)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)

    class Meta:
        db_table = 'signal_processing_master'
        # managed = False


class BearingFaultsMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    fault = models.BooleanField(default=False)
    misalignment_unbalance = models.BooleanField(default=False)
    looseness = models.BooleanField(default=False)
    speed = models.CharField(max_length=15, null=True, blank=True)
    bpfo = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    bpfi = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    bsf = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    ftf = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    fault_amp_thres = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    bpfo_coeff = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    bpfi_coeff = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    bsf_coeff = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    misalig_amp_thres = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    unbalance_amp_thres = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    looseness_amp_thres = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)

    class Meta:
        db_table = 'bearing_faults_master'
        # managed = False

class GearFaultsMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    fault = models.BooleanField(default=False)
    misalignment_unbalance = models.BooleanField(default=False)
    looseness = models.BooleanField(default=False)
    constant_speed = models.BooleanField(default=False, null=True, blank=True)
    no_of_gear_teeth = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    gear_ratio = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    gmp = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    misalig_amp_thres = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    unbalance_amp_thres = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    looseness_amp_thres = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)

    class Meta:
        db_table = 'gear_faults_master'
        # managed = False

class ACMotorFaultsMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    fault = models.BooleanField(default=False)
    misalignment_unbalance = models.BooleanField(default=False)
    looseness = models.BooleanField(default=False)
    line_freq = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    rotor_amp_thres = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    stator_amp_thres = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    misalig_amp_thres = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    unbalance_amp_thres = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    looseness_amp_thres = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)

    class Meta:
        db_table = 'ac_motor_faults_master'
        # managed = False

class PumpFanFaultsMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    fault = models.BooleanField(default=False)
    misalignment_unbalance = models.BooleanField(default=False)
    looseness = models.BooleanField(default=False)
    vanes_no_lower = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    vanes_no_upper = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    vpf_amp_thres = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    vane_fault_amp_thres = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    misalig_amp_thres = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    unbalance_amp_thres = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    looseness_amp_thres = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)

    class Meta:
        db_table = 'pump_fan_faults_master'
        # managed = False

class RPMReferenceMaster(models.Model):
    rpm_min = models.IntegerField()
    rpm_max = models.IntegerField()
    threshold = models.DecimalField(max_digits=5, decimal_places=2)
    creation_date=models.DateField(auto_now=True)

    class Meta:
        db_table = 'rpm_reference_master'
        # managed = False

class EnvelopeAmplitudeMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    fs = models.IntegerField()
    no_of_samples = models.IntegerField(null=True, blank=True)
    data = ArrayField(models.CharField(max_length=50000)) 
    axis = models.CharField(max_length=10)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'envelope_amplitude_master'
        # managed = False

class EnvelopeFrequencyMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    fs = models.IntegerField()
    no_of_samples = models.IntegerField(null=True, blank=True)
    data = ArrayField(models.CharField(max_length=50000))
    axis = models.CharField(max_length=10)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'envelope_frequency_master'
        # managed = False

class AssetTimestampData(models.Model):
    asset = models.ForeignKey(AssetMaster,on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    flag = models.BooleanField(default=False)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)

    class Meta:
        db_table = 'asset_timestamp'
        # managed = False  


class AssetHealthScore(models.Model):
    asset = models.ForeignKey(AssetMaster,on_delete=models.CASCADE)
    timestamp = models.DateTimeField(default=None)
    score = models.DecimalField(max_digits=5, decimal_places=2)
    fault_mode = models.CharField(max_length=15)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)

    class Meta:
        db_table = 'asset_score'
        # managed = False  


# class ThresholdValues(models.Model):
#     device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
#     velocity_rms = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
#     velocity_peak = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
#     velocity_peak_to_peak = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
#     velocity_kurtosis = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
#     acceleration_rms = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
#     acceleration_peak = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
#     acceleration_peak_to_peak = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
#     acceleration_kurtosis = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
#     displacement_rms = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
#     displacement_peak = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
#     displacement_peak_to_peak = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
#     displacement_kurtosis = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
#     one_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
#     two_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
#     three_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
#     four_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
#     five_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
#     six_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
#     seven_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
#     eight_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
#     nine_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
#     ten_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
#     org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
#     creation_date=models.DateField(auto_now=True)

#     class Meta:
#         db_table = 'threshold_values'
#         # managed = False  

class ThresholdValues(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    rms = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    peak = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    peak_to_peak = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    kurtosis = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    one_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    two_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    three_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    four_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    five_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    six_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    seven_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    eight_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    nine_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    ten_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    axis = models.CharField(max_length=10, null=True, blank=True)
    signal_type = models.CharField(max_length=50, null=True, blank=True)
    domain = models.CharField(max_length=50, null=True, blank=True)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)

    class Meta:
        db_table = 'threshold_values'
        # managed = False  

class AccelerationStatTimeMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    rms = models.DecimalField(max_digits=20, decimal_places=2)
    axis = models.CharField(max_length=10)
    peak = models.DecimalField(max_digits=20, decimal_places=2)
    peak_to_peak = models.DecimalField(max_digits=20, decimal_places=2)
    kurtosis = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    flag = models.BooleanField(default=False)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'acceleration_stat_time_master'
        # managed = False

# class AccelerationStatFreqMaster(models.Model):
#     device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
#     timestamp = models.DateTimeField()
#     rms = models.DecimalField(max_digits=20, decimal_places=2)
#     axis = models.CharField(max_length=10)
#     peak = models.DecimalField(max_digits=20, decimal_places=2)
#     peak_to_peak = models.DecimalField(max_digits=20, decimal_places=2)
#     kurtosis = models.DecimalField(max_digits=20, decimal_places=2, default=0)
#     org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
#     creation_date=models.DateField(auto_now=True)
#     class Meta:
#         db_table = 'acceleration_stat_freq_master'
#         # managed = False

class DisplacementStatTimeMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    timestamp = models.DateTimeField()
    rms = models.DecimalField(max_digits=20, decimal_places=2)
    axis = models.CharField(max_length=10)
    peak = models.DecimalField(max_digits=20, decimal_places=2)
    peak_to_peak = models.DecimalField(max_digits=20, decimal_places=2)
    kurtosis = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    flag = models.BooleanField(default=False)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'displacement_stat_time_master'
        # managed = False

# class DisplacementStatFreqMaster(models.Model):
#     device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
#     timestamp = models.DateTimeField()
#     rms = models.DecimalField(max_digits=20, decimal_places=2)
#     axis = models.CharField(max_length=10)
#     peak = models.DecimalField(max_digits=20, decimal_places=2)
#     peak_to_peak = models.DecimalField(max_digits=20, decimal_places=2)
#     kurtosis = models.DecimalField(max_digits=20, decimal_places=2, default=0)
#     org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
#     creation_date=models.DateField(auto_now=True)
#     class Meta:
#         db_table = 'displacement_stat_freq_master'
#         # managed = False

# need change
class AwsIotThingMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    thingName = models.CharField(max_length=200)
    deviceShadow = models.CharField(max_length=200, null=True, blank=True)
    thingArn  = models.CharField(max_length=200)
    thingId = models.CharField(max_length=200)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'aws_iot_thing_master'


class ThresholdCounterMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    rms_repetition = models.IntegerField(default=0)
    rms_counter = models.IntegerField(default=0)
    peak_repetition = models.IntegerField(default=0)
    peak_counter = models.IntegerField(default=0)
    peak_to_peak_repetition = models.IntegerField(default=0)
    peak_to_peak_counter = models.IntegerField(default=0)
    kurtosis_repetition = models.IntegerField(default=0)
    kurtosis_counter = models.IntegerField(default=0)
    one_amp_repetition = models.IntegerField(default=0)
    one_amp_counter = models.IntegerField(default=0)
    two_amp_repetition = models.IntegerField(default=0)
    two_amp_counter = models.IntegerField(default=0)
    three_amp_repetition = models.IntegerField(default=0)
    three_amp_counter = models.IntegerField(default=0)
    four_amp_repetition = models.IntegerField(default=0)
    four_amp_counter = models.IntegerField(default=0)
    five_amp_repetition = models.IntegerField(default=0)
    five_amp_counter = models.IntegerField(default=0)
    six_amp_repetition = models.IntegerField(default=0)
    six_amp_counter = models.IntegerField(default=0)
    seven_amp_repetition = models.IntegerField(default=0)
    seven_amp_counter = models.IntegerField(default=0)
    eight_amp_repetition = models.IntegerField(default=0)
    eight_amp_counter = models.IntegerField(default=0)
    nine_amp_repetition = models.IntegerField(default=0)
    nine_amp_counter = models.IntegerField(default=0)
    ten_amp_repetition = models.IntegerField(default=0)
    ten_amp_counter = models.IntegerField(default=0)
    axis = models.CharField(max_length=10, null=True, blank=True)
    signal_type = models.CharField(max_length=50, null=True, blank=True)
    domain = models.CharField(max_length=50, null=True, blank=True)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    # org_id = models.ForeignKey(CompanyMaster,on_delete=models.CASCADE)
    creation_date=models.DateField(auto_now=True)

    class Meta:
        db_table = 'threshold_counter_master'
        # managed = False 


class TemperatureMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    timestamp = models.DateTimeField(null=True, blank=True)
    temp = models.DecimalField(max_digits=20, decimal_places=2)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'temp_master'


class WiredSensorDataMaster(models.Model):
    device = models.ForeignKey(DeviceModelMaster,on_delete=models.CASCADE)
    timestamp = models.DateTimeField(null=True, blank=True)
    x_rms = models.DecimalField(max_digits=20, decimal_places=2)
    y_rms = models.DecimalField(max_digits=20, decimal_places=2)
    z_rms = models.DecimalField(max_digits=20, decimal_places=2)
    temp = models.DecimalField(max_digits=20, decimal_places=2)
    cmms_org = models.ForeignKey(CompanyMaster, to_field="comp_id_cmms", on_delete=models.CASCADE, default="619be26f5571c904ef4fa59b")
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'wired_data_master'