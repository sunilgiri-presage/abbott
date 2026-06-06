from email.policy import default
from sre_constants import MAX_UNTIL
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
# from phonenumber_field.modelfields import PhoneNumberField
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from rest_framework.authtoken.models import Token
from django.contrib.postgres.fields import ArrayField




class DeviceMountMaster(models.Model):
    composite_id = models.CharField(max_length=150, null=True, blank=True)
    is_linked = models.BooleanField(null=True, blank=True)
    point_name = models.CharField(max_length=150)
    mount_location = models.CharField(max_length=50)
    mount_type = models.CharField(max_length=50, null=True, blank=True)
    mount_material = models.CharField(max_length=50, null=True, blank=True)
    mount_direction = models.CharField(max_length=50, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    org_id = models.CharField(max_length=150, null=True, blank=True)
    mac_id = models.CharField(max_length=150, null=True, blank=True)
    image = models.CharField(max_length=200, null=True, blank=True)
    timezone = models.CharField(max_length=50, default="Asia/Calcutta")
    last_update = models.DateTimeField(auto_now=True, null=True)
    online = models.CharField(max_length=50, null=True, blank=True)
    class Meta:
        db_table = 'device_mount_master'
        # managed = False 

# need change
class DeviceModelMaster(models.Model):
    mount = models.ForeignKey(DeviceMountMaster,on_delete=models.CASCADE, db_column='composite_id')
    composite_key = models.CharField(max_length=150, primary_key=True)
    mac_id = models.CharField(max_length=150)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    org_id = models.CharField(max_length=150, null=True, blank=True)
    is_linked = models.BooleanField(default=True)
    creation_date=models.DateField(auto_now=True)
    last_update = models.DateTimeField(auto_now=True, null=True)
    class Meta:
        db_table = 'device_model_master'
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

class RawDataMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True)
    timestamp = models.DateTimeField(db_index=True)
    fs = models.IntegerField()
    no_of_samples = models.IntegerField( null=True, blank=True)
    raw_data = ArrayField(models.CharField(max_length=50000))
    # raw_data_updated = ArrayField(
    #     models.DecimalField(max_digits=10, decimal_places=3),
    #     null=True, 
    #     blank=True
    # )
    axis = models.CharField(max_length=10)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    last_update = models.DateTimeField(auto_now=True, null=True)
    class Meta:
        db_table = 'raw_data_master'
        # managed = False


class SensorLiveStatus(models.Model):
    composite_id = models.CharField(max_length=150, null=True, blank=True)
    last_update = models.DateTimeField(auto_now=True, null=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    class Meta:
        db_table = 'sensor_live_status'
        # managed = False

class SensorStatusNotifications(models.Model):
    mount = models.ForeignKey(DeviceMountMaster,on_delete=models.CASCADE)
    composite_id = models.CharField(max_length=150, null=True, blank=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date = models.DateTimeField(auto_now=True, null=True)
    read = models.BooleanField(default=False)
    online = models.BooleanField(default=False)
    last_update = models.DateTimeField(auto_now=True, null=True)
    class Meta:
        db_table = 'sensor_status_notifications'

class TemperatureMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True, db_index=True)
    timestamp = models.DateTimeField(null=True, blank=True, db_index=True)
    temp = models.DecimalField(max_digits=20, decimal_places=2)
    asset_id = models.CharField(max_length=150, null=True, blank=True, db_index=True)
    axis = models.CharField(max_length=20, default="temp")
    flag = models.BooleanField(default=False)
    mount_id = models.CharField(max_length=150, null=True, blank=True, db_index=True)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'temp_master'

@receiver(post_save, sender=TemperatureMaster)
def update_sensor_status(sender, instance, **kwargs):
    sensor_status, created = SensorLiveStatus.objects.get_or_create(composite_id=instance.composite, defaults=\
                                                                    {
                                                                        'composite_id': instance.composite,\
                                                                        'last_update': instance.creation_date,\
                                                                        'asset_id': instance.asset_id
                                                                        })
    if not created:
        sensor_status.last_update = instance.creation_date
        sensor_status.save()



class AccelerationTWFMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True, db_index=True)
    timestamp = models.DateTimeField(db_index=True)
    fs = models.IntegerField()
    no_of_samples = models.IntegerField( null=True, blank=True)
    data = ArrayField(models.CharField(max_length=50000)) 
    axis = models.CharField(max_length=10, db_index=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'acceleration_twf_master'
        # managed = False

class AccelerationSpectrumMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True, db_index=True)
    timestamp = models.DateTimeField(db_index=True)
    fs = models.IntegerField()
    no_of_samples = models.IntegerField( null=True, blank=True)
    data = ArrayField(models.CharField(max_length=50000))
    axis = models.CharField(max_length=10, db_index=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    high_pass = models.IntegerField(null=True, blank=True)
    low_pass = models.IntegerField(null=True, blank=True)
    rpm = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'acceleration_spectrum_master'
        # managed = False

class VelocityTWFMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True, db_index=True)
    timestamp = models.DateTimeField(db_index=True)
    fs = models.IntegerField()
    no_of_samples = models.IntegerField( null=True, blank=True)
    data = ArrayField(models.CharField(max_length=50000)) 
    axis = models.CharField(max_length=10, db_index=True)
    velocity_rms = models.DecimalField(max_digits=20, decimal_places=2)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'velocity_twf_master'
        # managed = False

class VelocitySpectrumMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True, db_index=True)
    timestamp = models.DateTimeField(db_index=True)
    fs = models.IntegerField()
    no_of_samples = models.IntegerField( null=True, blank=True)
    data = ArrayField(models.CharField(max_length=50000))
    axis = models.CharField(max_length=10, db_index=True)
    velocity_rms = models.DecimalField(max_digits=20, decimal_places=2)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    high_pass = models.IntegerField(null=True, blank=True)
    low_pass = models.IntegerField(null=True, blank=True)
    rpm = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'velocity_spectrum_master'
        # managed = False

class DisplacementTWFMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True, db_index=True)
    timestamp = models.DateTimeField(db_index=True)
    fs = models.IntegerField()
    no_of_samples = models.IntegerField( null=True, blank=True)
    data = ArrayField(models.CharField(max_length=50000))
    axis = models.CharField(max_length=10, db_index=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'displacement_twf_master'
        # managed = False

class DisplacementSpectrumMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True, db_index=True)
    timestamp = models.DateTimeField(db_index=True)
    fs = models.IntegerField()
    no_of_samples = models.IntegerField( null=True, blank=True)
    data = ArrayField(models.CharField(max_length=50000))
    axis = models.CharField(max_length=10, db_index=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    high_pass = models.IntegerField(null=True, blank=True)
    low_pass = models.IntegerField(null=True, blank=True)
    rpm = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'displacement_spectrum_master'
        # managed = False


class VelocityStatTimeMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True, db_index=True)
    timestamp = models.DateTimeField(db_index=True)
    rms = models.DecimalField(max_digits=20, decimal_places=2)
    axis = models.CharField(max_length=10, db_index=True)
    peak = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    peak_to_peak = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    kurtosis = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    flag = models.BooleanField(default=False)
    rms_only = models.BooleanField(default=False, db_index=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    mount_id = models.CharField(max_length=150, null=True, blank=True, db_index=True)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'velocity_stat_time_master'
        # managed = False

# class VelocityStatFreqMaster(models.Model):
#     composite =  models.CharField(max_length=150, null=True, blank=True)
#     timestamp = models.DateTimeField()
#     rms = models.DecimalField(max_digits=20, decimal_places=2)
#     axis = models.CharField(max_length=10)
#     peak = models.DecimalField(max_digits=20, decimal_places=2)
#     peak_to_peak = models.DecimalField(max_digits=20, decimal_places=2)
#     kurtosis = models.DecimalField(max_digits=20, decimal_places=2, default=0)
#     flag = models.BooleanField(default=False)
#     asset_id = models.CharField(max_length=150, null=True, blank=True)
#     creation_date=models.DateField(auto_now=True)
#     class Meta:
#         db_table = 'velocity_stat_freq_master'


class AccelerationHarmonicsMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True)
    timestamp = models.DateTimeField(db_index=True)
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
    flag = models.BooleanField(default=False)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'acceleration_harmonics_master'
        # managed = False

class VelocityHarmonicsMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True)
    timestamp = models.DateTimeField(db_index=True)
    axis = models.CharField(max_length=10)
    phase = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    half_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    half_freq = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    one_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    one_freq = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    one_half_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    one_half_freq = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    two_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    two_freq = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    two_half_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    two_half_freq = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    three_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    three_freq = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    three_half_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    three_half_freq = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    four_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    four_freq = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    four_half_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    four_half_freq = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    five_amp = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    five_freq = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)



    flag = models.BooleanField(default=False)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'velocity_harmonics_master'
        # managed = False

class DisplacementHarmonicsMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True)
    timestamp = models.DateTimeField(db_index=True)
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
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'displacement_harmonics_master'
        # managed = False

class HardwareMaster(models.Model):
    mount = models.ForeignKey(DeviceMountMaster,on_delete=models.CASCADE)
    composite_id = models.CharField(max_length=150, null=True, blank=True)
    hardware_type = models.CharField(max_length=15, default=None, null=True, blank=True)
    hardware_components = ArrayField(models.CharField(max_length=50), default=None, null=True, blank=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    last_update = models.DateTimeField(auto_now=True, null=True)
    class Meta:
        db_table = 'hardware_master'
        # managed = False

class FirmwareMaster(models.Model):
    mount = models.ForeignKey(DeviceMountMaster,on_delete=models.CASCADE)
    composite_id = models.CharField(max_length=150, null=True, blank=True)
    sampling_rate = models.IntegerField(null=True, blank=True)
    acoustic_sampling_rate = models.IntegerField(null=True, blank=True)
    sampling_rate_edge = models.IntegerField(null=True, blank=True)
    no_of_samples = models.IntegerField(null=True, blank=True)
    no_of_samples_edge = models.IntegerField(null=True, blank=True)
    upload_time = models.CharField(max_length=150, null=True, blank=True)
    sleep_time = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    rms_data_interval = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    sensitivity = models.IntegerField(null=True, blank=True)
    wired_rms_freq = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    bleRangeMode = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    last_update = models.DateTimeField(auto_now=True, null=True)
    class Meta:
        db_table = 'firmware_master'
        # managed = False

class EdgeCalculationParams(models.Model):
    mount = models.ForeignKey(DeviceMountMaster,on_delete=models.CASCADE)
    composite_id = models.CharField(max_length=150, null=True, blank=True)
    sensitivity = models.IntegerField(null=True, blank=True)
    sampling_rate = models.IntegerField(null=True, blank=True)
    sleep_time = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    counter = models.IntegerField(null=True, blank=True)
    edgeAlarmTimeOut = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    acc_rms_x = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    acc_rms_y = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    acc_rms_z = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    velocity_x = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    velocity_y = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    velocity_z = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    temp = models.IntegerField(null=True, blank=True)
    acc_pp_x = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    acc_pp_y = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    acc_pp_z = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    x_threshold = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    y_threshold = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    z_threshold = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    last_update = models.DateTimeField(auto_now=True, null=True)
    class Meta:
        db_table = 'edge_params_master'
        # managed = False
        

class SignalProcessingMaster(models.Model):
    mount = models.ForeignKey(DeviceMountMaster,on_delete=models.CASCADE)
    composite_id = models.CharField(max_length=150, null=True, blank=True)
    high_pass = models.IntegerField(null=True, blank=True)
    low_pass = models.IntegerField(null=True, blank=True)
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
    rpm = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
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
    sensitivity = models.IntegerField(null=True, blank=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    last_update = models.DateTimeField(auto_now=True, null=True)
    class Meta:
        db_table = 'signal_processing_master'
        # managed = False


class BearingFaultsMaster(models.Model):
    mount = models.ForeignKey(DeviceMountMaster,on_delete=models.CASCADE)
    composite_id = models.CharField(max_length=150, null=True, blank=True)
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
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    last_update = models.DateTimeField(auto_now=True, null=True)
    class Meta:
        db_table = 'bearing_faults_master'
        # managed = False

class GearFaultsMaster(models.Model):
    mount = models.ForeignKey(DeviceMountMaster,on_delete=models.CASCADE)
    composite_id = models.CharField(max_length=150, null=True, blank=True)
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
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    last_update = models.DateTimeField(auto_now=True, null=True)
    class Meta:
        db_table = 'gear_faults_master'
        # managed = False

class ACMotorFaultsMaster(models.Model):
    mount = models.ForeignKey(DeviceMountMaster,on_delete=models.CASCADE)
    composite_id = models.CharField(max_length=150, null=True, blank=True)
    fault = models.BooleanField(default=False)
    misalignment_unbalance = models.BooleanField(default=False)
    looseness = models.BooleanField(default=False)
    line_freq = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    rotor_amp_thres = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    stator_amp_thres = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    misalig_amp_thres = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    unbalance_amp_thres = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    looseness_amp_thres = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    last_update = models.DateTimeField(auto_now=True, null=True)
    class Meta:
        db_table = 'ac_motor_faults_master'
        # managed = False

class PumpFanFaultsMaster(models.Model):
    mount = models.ForeignKey(DeviceMountMaster,on_delete=models.CASCADE)
    composite_id = models.CharField(max_length=150, null=True, blank=True)
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
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    last_update = models.DateTimeField(auto_now=True, null=True)
    class Meta:
        db_table = 'pump_fan_faults_master'
        # managed = False

class RPMReferenceMaster(models.Model):
    rpm_min = models.IntegerField()
    rpm_max = models.IntegerField()
    threshold = models.DecimalField(max_digits=5, decimal_places=2)
    creation_date=models.DateField(auto_now=True)
    last_update = models.DateTimeField(auto_now=True, null=True)
    class Meta:
        db_table = 'rpm_reference_master'
        # managed = False

class EnvelopeTWFMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True)
    timestamp = models.DateTimeField(db_index=True)
    fs = models.IntegerField()
    no_of_samples = models.IntegerField(null=True, blank=True)
    data = ArrayField(models.CharField(max_length=50000)) 
    axis = models.CharField(max_length=10)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'envelope_twf_master'
        # managed = False

class EnvelopeSpectrumMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True)
    timestamp = models.DateTimeField(db_index=True)
    fs = models.IntegerField()
    no_of_samples = models.IntegerField(null=True, blank=True)
    data = ArrayField(models.CharField(max_length=50000))
    axis = models.CharField(max_length=10)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'envelope_spectrum_master'
        # managed = False


# class ThresholdValues(models.Model):
#     composite =  models.CharField(max_length=150, null=True, blank=True)
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
#     creation_date=models.DateField(auto_now=True)

#     class Meta:
#         db_table = 'threshold_values'
#         # managed = False  

class ThresholdValues(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True)
    rms_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    peak_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    peak_to_peak_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    kurtosis_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    one_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    two_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    three_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    four_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    temp_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    rms_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    peak_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    peak_to_peak_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    kurtosis_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    one_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    two_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    three_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    four_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    temp_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    rms_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    peak_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    peak_to_peak_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    kurtosis_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    one_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    two_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    three_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    four_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    temp_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
    axis = models.CharField(max_length=10, null=True, blank=True)
    signal_type = models.CharField(max_length=50, null=True, blank=True)
    domain = models.CharField(max_length=50, null=True, blank=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    mount_id = models.CharField(max_length=20, null=True, blank=True)
    last_update = models.DateTimeField(auto_now=True, null=True)
    class Meta:
        db_table = 'threshold_values'
        # managed = False  

class AccelerationStatTimeMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True, db_index=True)
    timestamp = models.DateTimeField(db_index=True)
    rms = models.DecimalField(max_digits=20, decimal_places=2)
    axis = models.CharField(max_length=10, db_index=True)
    peak = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    peak_to_peak = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    kurtosis = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    flag = models.BooleanField(default=False)
    rms_only = models.BooleanField(default=False, db_index=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    mount_id = models.CharField(max_length=150, null=True, blank=True, db_index=True)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'acceleration_stat_time_master'
        # managed = False

class FrequencyDomainFeatuers(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True)
    timestamp = models.DateTimeField(db_index=True)
    ehnr = models.DecimalField(max_digits=20, decimal_places=2)
    axis = models.CharField(max_length=10)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'frequency_domain_featuers'
        # managed = False

class DisplacementStatTimeMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True, db_index=True)
    timestamp = models.DateTimeField(db_index=True)
    rms = models.DecimalField(max_digits=20, decimal_places=2)
    axis = models.CharField(max_length=10, db_index=True)
    peak = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    peak_to_peak = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    kurtosis = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    flag = models.BooleanField(default=False)
    rms_only = models.BooleanField(default=False, db_index=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    mount_id = models.CharField(max_length=150, null=True, blank=True, db_index=True)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'displacement_stat_time_master'
        # managed = False

# class DisplacementStatFreqMaster(models.Model):
#     composite =  models.CharField(max_length=150, null=True, blank=True)
#     timestamp = models.DateTimeField()
#     rms = models.DecimalField(max_digits=20, decimal_places=2)
#     axis = models.CharField(max_length=10)
#     peak = models.DecimalField(max_digits=20, decimal_places=2)
#     peak_to_peak = models.DecimalField(max_digits=20, decimal_places=2)
#     kurtosis = models.DecimalField(max_digits=20, decimal_places=2, default=0)
#     flag = models.BooleanField(default=False)
#     asset_id = models.CharField(max_length=150, null=True, blank=True)
#     creation_date=models.DateField(auto_now=True)
#     class Meta:
#         db_table = 'displacement_stat_freq_master'
#         # managed = False

# need change
class AwsIotThingMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True)
    thingName = models.CharField(max_length=200)
    deviceShadow = models.CharField(max_length=200, null=True, blank=True)
    thingArn  = models.CharField(max_length=200)
    thingId = models.CharField(max_length=200)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    last_update = models.DateTimeField(auto_now=True, null=True)
    class Meta:
        db_table = 'aws_iot_thing_master'


def default_values():
    return {
        "rms_amp_level_1": None,
        "peak_amp_level_1": None,
        "peak_to_peak_amp_level_1": None,
        "kurtosis_amp_level_1": None,
        "one_amp_level_1": None,
        "two_amp_level_1": None,
        "three_amp_level_1": None,
        "four_amp_level_1": None,
        "temp_amp_level_1": None,
        "rms_amp_level_2": None,
        "peak_amp_level_2": None,
        "peak_to_peak_amp_level_2": None,
        "kurtosis_amp_level_2": None,
        "one_amp_level_2": None,
        "two_amp_level_2": None,
        "three_amp_level_2": None,
        "four_amp_level_2": None,
        "temp_amp_level_2": None,
        "rms_amp_level_3": None,
        "peak_amp_level_3": None,
        "peak_to_peak_amp_level_3": None,
        "kurtosis_amp_level_3": None,
        "one_amp_level_3": None,
        "two_amp_level_3": None,
        "three_amp_level_3": None,
        "four_amp_level_3": None,
        "temp_amp_level_3": None,
    }

class ThresholdCounterMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True)
    rms_amp_repetition_level_1 = models.IntegerField(default=0)
    rms_amp_counter_level_1 = models.IntegerField(default=0)
    peak_amp_repetition_level_1 = models.IntegerField(default=0)
    peak_amp_counter_level_1 = models.IntegerField(default=0)
    peak_to_peak_amp_repetition_level_1 = models.IntegerField(default=0)
    peak_to_peak_amp_counter_level_1 = models.IntegerField(default=0)
    kurtosis_amp_repetition_level_1 = models.IntegerField(default=0)
    kurtosis_amp_counter_level_1 = models.IntegerField(default=0)
    one_amp_repetition_level_1 = models.IntegerField(default=0)
    one_amp_counter_level_1 = models.IntegerField(default=0)
    two_amp_repetition_level_1 = models.IntegerField(default=0)
    two_amp_counter_level_1 = models.IntegerField(default=0)
    three_amp_repetition_level_1 = models.IntegerField(default=0)
    three_amp_counter_level_1 = models.IntegerField(default=0)
    four_amp_repetition_level_1 = models.IntegerField(default=0)
    four_amp_counter_level_1 = models.IntegerField(default=0)
    temp_amp_repetition_level_1 = models.IntegerField(default=0)
    temp_amp_counter_level_1 = models.IntegerField(default=0)
    rms_amp_repetition_level_2 = models.IntegerField(default=0)
    rms_amp_counter_level_2 = models.IntegerField(default=0)
    peak_amp_repetition_level_2 = models.IntegerField(default=0)
    peak_amp_counter_level_2 = models.IntegerField(default=0)
    peak_to_peak_amp_repetition_level_2 = models.IntegerField(default=0)
    peak_to_peak_amp_counter_level_2 = models.IntegerField(default=0)
    kurtosis_amp_repetition_level_2 = models.IntegerField(default=0)
    kurtosis_amp_counter_level_2 = models.IntegerField(default=0)
    one_amp_repetition_level_2 = models.IntegerField(default=0)
    one_amp_counter_level_2 = models.IntegerField(default=0)
    two_amp_repetition_level_2 = models.IntegerField(default=0)
    two_amp_counter_level_2 = models.IntegerField(default=0)
    three_amp_repetition_level_2 = models.IntegerField(default=0)
    three_amp_counter_level_2 = models.IntegerField(default=0)
    four_amp_repetition_level_2 = models.IntegerField(default=0)
    four_amp_counter_level_2 = models.IntegerField(default=0)
    temp_amp_repetition_level_2 = models.IntegerField(default=0)
    temp_amp_counter_level_2 = models.IntegerField(default=0)
    rms_amp_repetition_level_3 = models.IntegerField(default=0)
    rms_amp_counter_level_3 = models.IntegerField(default=0)
    peak_amp_repetition_level_3 = models.IntegerField(default=0)
    peak_amp_counter_level_3 = models.IntegerField(default=0)
    peak_to_peak_amp_repetition_level_3 = models.IntegerField(default=0)
    peak_to_peak_amp_counter_level_3 = models.IntegerField(default=0)
    kurtosis_amp_repetition_level_3 = models.IntegerField(default=0)
    kurtosis_amp_counter_level_3 = models.IntegerField(default=0)
    one_amp_repetition_level_3 = models.IntegerField(default=0)
    one_amp_counter_level_3 = models.IntegerField(default=0)
    two_amp_repetition_level_3 = models.IntegerField(default=0)
    two_amp_counter_level_3 = models.IntegerField(default=0)
    three_amp_repetition_level_3 = models.IntegerField(default=0)
    three_amp_counter_level_3 = models.IntegerField(default=0)
    four_amp_repetition_level_3 = models.IntegerField(default=0)
    four_amp_counter_level_3 = models.IntegerField(default=0)
    temp_amp_repetition_level_3 = models.IntegerField(default=0)
    temp_amp_counter_level_3 = models.IntegerField(default=0)
    axis = models.CharField(max_length=10, null=True, blank=True)
    signal_type = models.CharField(max_length=50, null=True, blank=True)
    domain = models.CharField(max_length=50, null=True, blank=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    last_update = models.DateTimeField(auto_now=True, null=True)
    rms_amp_repetition_level_1_timestamp = models.DateTimeField(null=True, blank=True)
    peak_amp_repetition_level_1_timestamp = models.DateTimeField(null=True, blank=True)
    peak_to_peak_amp_repetition_level_1_timestamp = models.DateTimeField(null=True, blank=True)
    kurtosis_amp_repetition_level_1_timestamp = models.DateTimeField(null=True, blank=True)
    one_amp_repetition_level_1_timestamp = models.DateTimeField(null=True, blank=True)
    two_amp_repetition_level_1_timestamp = models.DateTimeField(null=True, blank=True)
    three_amp_repetition_level_1_timestamp = models.DateTimeField(null=True, blank=True)
    four_amp_repetition_level_1_timestamp = models.DateTimeField(null=True, blank=True)
    temp_amp_repetition_level_1_timestamp = models.DateTimeField(null=True, blank=True)
    rms_amp_repetition_level_2_timestamp = models.DateTimeField(null=True, blank=True)
    peak_amp_repetition_level_2_timestamp = models.DateTimeField(null=True, blank=True)
    peak_to_peak_amp_repetition_level_2_timestamp = models.DateTimeField(null=True, blank=True)
    kurtosis_amp_repetition_level_2_timestamp = models.DateTimeField(null=True, blank=True)
    one_amp_repetition_level_2_timestamp = models.DateTimeField(null=True, blank=True)
    two_amp_repetition_level_2_timestamp = models.DateTimeField(null=True, blank=True)
    three_amp_repetition_level_2_timestamp = models.DateTimeField(null=True, blank=True)
    four_amp_repetition_level_2_timestamp = models.DateTimeField(null=True, blank=True)
    temp_amp_repetition_level_2_timestamp = models.DateTimeField(null=True, blank=True)
    rms_amp_repetition_level_3_timestamp = models.DateTimeField(null=True, blank=True)
    peak_amp_repetition_level_3_timestamp = models.DateTimeField(null=True, blank=True)
    peak_to_peak_amp_repetition_level_3_timestamp = models.DateTimeField(null=True, blank=True)
    kurtosis_amp_repetition_level_3_timestamp = models.DateTimeField(null=True, blank=True)
    one_amp_repetition_level_3_timestamp = models.DateTimeField(null=True, blank=True)
    two_amp_repetition_level_3_timestamp = models.DateTimeField(null=True, blank=True)
    three_amp_repetition_level_3_timestamp = models.DateTimeField(null=True, blank=True)
    four_amp_repetition_level_3_timestamp = models.DateTimeField(null=True, blank=True)
    temp_amp_repetition_level_3_timestamp = models.DateTimeField(null=True, blank=True)
    mount_id = models.CharField(max_length=20, null=True, blank=True)
    values = models.JSONField(default=default_values, null=True, blank=True)
    class Meta:
        db_table = 'threshold_counter_master'
        # managed = False 


# class TemperatureMaster(models.Model):
#     composite =  models.CharField(max_length=150, null=True, blank=True, db_index=True)
#     timestamp = models.DateTimeField(null=True, blank=True, db_index=True)
#     temp = models.DecimalField(max_digits=20, decimal_places=2)
#     asset_id = models.CharField(max_length=150, null=True, blank=True, db_index=True)
#     axis = models.CharField(max_length=20, default="temp")
#     flag = models.BooleanField(default=False)
#     creation_date=models.DateField(auto_now=True)
#     class Meta:
#         db_table = 'temp_master'


class WiredSensorDataMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True)
    timestamp = models.DateTimeField(null=True, blank=True)
    x_rms = models.DecimalField(max_digits=20, decimal_places=2)
    y_rms = models.DecimalField(max_digits=20, decimal_places=2)
    z_rms = models.DecimalField(max_digits=20, decimal_places=2)
    temp = models.DecimalField(max_digits=20, decimal_places=2)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'wired_data_master'

class MobileAppKpiThreshold(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    v_rms_level_1 = models.DecimalField(max_digits=20, decimal_places=2)
    v_rms_level_2 = models.DecimalField(max_digits=20, decimal_places=2)
    v_rms_level_3 = models.DecimalField(max_digits=20, decimal_places=2)
    a_envelope_level_1 = models.DecimalField(max_digits=20, decimal_places=2)
    a_envelope_level_2 = models.DecimalField(max_digits=20, decimal_places=2)
    a_envelope_level_3 = models.DecimalField(max_digits=20, decimal_places=2)
    temp_level_1 = models.DecimalField(max_digits=20, decimal_places=2)
    temp_level_2 = models.DecimalField(max_digits=20, decimal_places=2)
    temp_level_3 = models.DecimalField(max_digits=20, decimal_places=2)
    axis = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    last_update = models.DateTimeField(auto_now=True, null=True)
    class Meta:
        db_table = "mobile_app_kpi_threshold"


class SpectrumChartDataMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True, db_index=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    timestamp = models.DateTimeField(db_index=True)
    acceleration = ArrayField(models.CharField(max_length=50000))
    velocity = ArrayField(models.CharField(max_length=50000))
    displacement = ArrayField(models.CharField(max_length=50000))
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = "spectrum_x_data"


class KPIScoreMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True)
    timestamp = models.DateTimeField(db_index=True)
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
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    flag = models.BooleanField(default=False)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'kpi_score_master'
        # managed = False  

# class AssetScoreMaster(models.Model):
#     composite =  models.CharField(max_length=150, null=True, blank=True)
#     timestamp = models.DateTimeField()
#     axis = models.CharField(max_length=10, null=True, blank=True)
#     signal_type = models.CharField(max_length=50, null=True, blank=True)
#     asset_id = models.CharField(max_length=150, null=True, blank=True)
#     creation_date=models.DateField(auto_now=True)



class BearingDetailMaster(models.Model):
    mount = models.ForeignKey(DeviceMountMaster,on_delete=models.CASCADE)
    composite_id = models.CharField(max_length=150, null=True, blank=True)
    bearing_number = models.CharField(max_length=150, null=True, blank=True)
    bpfo = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    bpfi = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    bsf = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    ftf = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    last_update = models.DateTimeField(auto_now=True, null=True)
    class Meta:
        db_table = 'bearing_detail_master'
        # managed = False  

class AlarmHistoryMaster(models.Model):
    composite  = models.CharField(max_length=150, null=True, blank=True)
    timestamp = models.DateTimeField(db_index=True)
    signal_type = models.CharField(max_length=150, null=True, blank=True)
    trend_type = models.CharField(max_length=150, null=True, blank=True)
    axis = models.CharField(max_length=10, null=True, blank=True)
    priority = models.CharField(max_length=50, null=True, blank=True)
    sensor_location = models.CharField(max_length=150, null=True, blank=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    threshold_value = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    observed_value = models.DecimalField(max_digits=20, decimal_places=5, null=True, blank=True)
    addressed = models.BooleanField(default=False)
    fault_flag = models.BooleanField(default=False)
    creation_date=models.DateTimeField(auto_now=True)
    class Meta:
        db_table = 'alarm_history_master'
        # managed = False  


class AlarmQueueMaster(models.Model):
    ALARM_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('send', 'Send'),
        ('rejected', 'Rejected'),
    ]

    composite = models.CharField(max_length=150)
    signal_type = models.CharField(max_length=50)
    trend_type = models.CharField(max_length=50)
    axis = models.CharField(max_length=10)
    priority = models.CharField(max_length=20)
    sensor_location = models.CharField(max_length=200)
    asset_id = models.CharField(max_length=150)
    org_id = models.CharField(max_length=150, null=True, blank=True)
    asset_name = models.CharField(max_length=200, null=True, blank=True)
    location_name = models.CharField(max_length=200, null=True, blank=True)
    company_name = models.CharField(max_length=200, null=True, blank=True)
    timestamp = models.DateTimeField()
    threshold_value = models.FloatField()
    observed_value = models.FloatField()
    status = models.CharField(max_length=20, choices=ALARM_STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    approved_by = models.CharField(max_length=100, null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    mail_sent_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    class Meta:
        db_table = 'alarm_queue_master'
        ordering = ['-created_at']


class AssetDiagnosticReportMaster(models.Model):
    STATUS_CHOICES = [
        ('completed', 'Completed'),
        ('no_faults', 'No Faults'),
        ('failed', 'Failed'),
    ]

    TRIGGER_SOURCE_CHOICES = [
        ('api', 'API'),
        ('alarm_history', 'Alarm History'),
        ('alarm_queue', 'Alarm Queue'),
    ]

    asset_id = models.CharField(max_length=150, null=True, blank=True, db_index=True)
    trigger_source = models.CharField(max_length=50, choices=TRIGGER_SOURCE_CHOICES, default='api')
    alarm_history = models.ForeignKey(AlarmHistoryMaster, on_delete=models.SET_NULL, null=True, blank=True)
    alarm_queue = models.ForeignKey(AlarmQueueMaster, on_delete=models.SET_NULL, null=True, blank=True)
    alarm_snapshot = models.JSONField(null=True, blank=True)
    diagnostic_input = models.JSONField(null=True, blank=True)
    report_json = models.JSONField(null=True, blank=True)
    response_json = models.JSONField(null=True, blank=True)
    result = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')
    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'asset_diagnostic_report_master'
        ordering = ['-created_at']

class SensorOrientationMaster(models.Model):
    position = models.CharField(max_length=150, null=True, blank=True)
    x = models.CharField(max_length=50, null=True, blank=True)
    y = models.CharField(max_length=50, null=True, blank=True)
    z = models.CharField(max_length=50, null=True, blank=True)
    last_update = models.DateTimeField(auto_now=True, null=True)
    class Meta:
        db_table = 'sensor_orientation_master'
        # managed = False  

class AssetHealthMaster(models.Model):
    asset_id = models.CharField(max_length=150, null=True, blank=True, db_index=True)
    org_id = models.CharField(max_length=150, null=True, blank=True)
    status = models.CharField(max_length=150, null=True, blank=True)
    score = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    creation_date=models.DateTimeField(auto_now=True)
    class Meta:
        db_table = 'asset_health_master'

class AssetHealthHistoryMaster(models.Model):
    asset_id = models.CharField(max_length=150, null=True, blank=True, db_index=True)
    org_id = models.CharField(max_length=150, null=True, blank=True)
    status = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'asset_health_history_master'


class SensorPositionMaster(models.Model):
    sensor_type = models.CharField(max_length=150, null=True, blank=True)
    orientation = models.JSONField(max_length=200, null=True, blank=True)
    last_update = models.DateTimeField(auto_now=True, null=True)
    class Meta:
        db_table = 'sensor_position_master'
        # managed = False  


class BearingFaultFrequenciesMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True)
    timestamp = models.DateTimeField(db_index=True)
    axis = models.CharField(max_length=10)
    bpfo_amp = ArrayField(models.DecimalField(max_digits=50, decimal_places=4), null=True, blank=True)
    bpfo_freq = ArrayField(models.DecimalField(max_digits=50, decimal_places=4), null=True, blank=True)
    bpfi_amp = ArrayField(models.DecimalField(max_digits=50, decimal_places=4), null=True, blank=True)
    bpfi_freq = ArrayField(models.DecimalField(max_digits=50, decimal_places=4), null=True, blank=True)
    bsf_amp = ArrayField(models.DecimalField(max_digits=50, decimal_places=4), null=True, blank=True)
    bsf_freq = ArrayField(models.DecimalField(max_digits=50, decimal_places=4), null=True, blank=True)
    ftf_amp = ArrayField(models.DecimalField(max_digits=50, decimal_places=4), null=True, blank=True)
    ftf_freq = ArrayField(models.DecimalField(max_digits=50, decimal_places=4), null=True, blank=True)
    signal_type = models.CharField(max_length=50, null=True, blank=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'bearing_fault_frequencies_master'

class DynamicThresholdType(models.Model):

    asset_id = models.CharField(max_length=150, null=True, blank=True)
    is_dynamic = models.BooleanField(default=True)
    creation_date = models.DateField(auto_now=True)
    last_update = models.DateTimeField(auto_now=True, null=True)
    class Meta:
        db_table = 'threshold_type'


class AcousticsMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True, db_index=True)
    timestamp = models.DateTimeField(null=True, blank=True, db_index=True)
    acoustic_db = models.DecimalField(max_digits=20, decimal_places=2)
    acoustic_rms = models.DecimalField(max_digits=20, decimal_places=2)
    acoustic_rms_10k = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    acoustic_rms_20k = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    axis = models.CharField(max_length=20, default="a")
    flag = models.BooleanField(default=False)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'acoustic_master'

class AcousticsSpectrumMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True, db_index=True)
    timestamp = models.DateTimeField(null=True, blank=True, db_index=True)
    twf_data = ArrayField(models.CharField(max_length=50000)) 
    spectrum_data = ArrayField(models.CharField(max_length=50000))
    spectrum_data_10k = ArrayField(models.CharField(max_length=50000), null=True, blank=True)
    spectrum_data_20k = ArrayField(models.CharField(max_length=50000), null=True, blank=True)
    frequency_data = ArrayField(models.CharField(max_length=50000))
    frequency_data_10k = ArrayField(models.CharField(max_length=50000), null=True, blank=True)
    frequency_data_20k = ArrayField(models.CharField(max_length=50000), null=True, blank=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    axis = models.CharField(max_length=20, default="a")
    flag = models.BooleanField(default=False)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'acoustic_spectrum_master'





# class EmailHistoryMaster(models.Model):

#     composite = models.CharField(max_length=150)
#     asset_id = models.CharField(max_length=150, null=True, blank=True)
#     asset_name = models.CharField(max_length=150, null=True, blank=True)
#     location_name = models.CharField(max_length=150, null=True, blank=True)
#     top_asset_name = models.CharField(max_length=150, null=True, blank=True)
#     user_email = ArrayField(models.CharField(max_length=150))
#     user_id = ArrayField(models.CharField(max_length=150))
#     signal_type = models.CharField(max_length=150, null=True, blank=True)
#     trend_type = models.CharField

#     creation_date = models.DateField(auto_now=True)

#     class Meta:
#         db_table = 'threshold_type'



# class DynamicThresholdValues(models.Model):
#     composite =  models.CharField(max_length=150, null=True, blank=True)
#     rms_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
#     peak_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
#     peak_to_peak_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
#     kurtosis_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
#     one_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
#     two_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
#     three_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
#     four_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
#     temp_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
#     rms_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
#     peak_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
#     peak_to_peak_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
#     kurtosis_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
#     one_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
#     two_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
#     three_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
#     four_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
#     temp_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
#     rms_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
#     peak_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
#     peak_to_peak_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
#     kurtosis_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
#     one_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
#     two_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
#     three_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
#     four_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=5, default=0)
#     temp_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=5, default=0)

#     axis = models.CharField(max_length=10, null=True, blank=True)
#     signal_type = models.CharField(max_length=50, null=True, blank=True)
#     domain = models.CharField(max_length=50, null=True, blank=True)
#     asset_id = models.CharField(max_length=150, null=True, blank=True)
#     creation_date=models.DateField(auto_now=True)

#     class Meta:
#         db_table = 'dynamic_threshold_values'
#         # managed = False  



# class DynamicThresholdCounterMaster(models.Model):
#     composite =  models.CharField(max_length=150, null=True, blank=True)
#     rms_amp_repetition_level_1 = models.IntegerField(default=0)
#     rms_amp_counter_level_1 = models.IntegerField(default=0)
#     peak_amp_repetition_level_1 = models.IntegerField(default=0)
#     peak_amp_counter_level_1 = models.IntegerField(default=0)
#     peak_to_peak_amp_repetition_level_1 = models.IntegerField(default=0)
#     peak_to_peak_amp_counter_level_1 = models.IntegerField(default=0)
#     kurtosis_amp_repetition_level_1 = models.IntegerField(default=0)
#     kurtosis_amp_counter_level_1 = models.IntegerField(default=0)
#     one_amp_repetition_level_1 = models.IntegerField(default=0)
#     one_amp_counter_level_1 = models.IntegerField(default=0)
#     two_amp_repetition_level_1 = models.IntegerField(default=0)
#     two_amp_counter_level_1 = models.IntegerField(default=0)
#     three_amp_repetition_level_1 = models.IntegerField(default=0)
#     three_amp_counter_level_1 = models.IntegerField(default=0)
#     four_amp_repetition_level_1 = models.IntegerField(default=0)
#     four_amp_counter_level_1 = models.IntegerField(default=0)
#     temp_amp_repetition_level_1 = models.IntegerField(default=0)
#     temp_amp_counter_level_1 = models.IntegerField(default=0)
#     rms_amp_repetition_level_2 = models.IntegerField(default=0)
#     rms_amp_counter_level_2 = models.IntegerField(default=0)
#     peak_amp_repetition_level_2 = models.IntegerField(default=0)
#     peak_amp_counter_level_2 = models.IntegerField(default=0)
#     peak_to_peak_amp_repetition_level_2 = models.IntegerField(default=0)
#     peak_to_peak_amp_counter_level_2 = models.IntegerField(default=0)
#     kurtosis_amp_repetition_level_2 = models.IntegerField(default=0)
#     kurtosis_amp_counter_level_2 = models.IntegerField(default=0)
#     one_amp_repetition_level_2 = models.IntegerField(default=0)
#     one_amp_counter_level_2 = models.IntegerField(default=0)
#     two_amp_repetition_level_2 = models.IntegerField(default=0)
#     two_amp_counter_level_2 = models.IntegerField(default=0)
#     three_amp_repetition_level_2 = models.IntegerField(default=0)
#     three_amp_counter_level_2 = models.IntegerField(default=0)
#     four_amp_repetition_level_2 = models.IntegerField(default=0)
#     four_amp_counter_level_2 = models.IntegerField(default=0)
#     temp_amp_repetition_level_2 = models.IntegerField(default=0)
#     temp_amp_counter_level_2 = models.IntegerField(default=0)
#     rms_amp_repetition_level_3 = models.IntegerField(default=0)
#     rms_amp_counter_level_3 = models.IntegerField(default=0)
#     peak_amp_repetition_level_3 = models.IntegerField(default=0)
#     peak_amp_counter_level_3 = models.IntegerField(default=0)
#     peak_to_peak_amp_repetition_level_3 = models.IntegerField(default=0)
#     peak_to_peak_amp_counter_level_3 = models.IntegerField(default=0)
#     kurtosis_amp_repetition_level_3 = models.IntegerField(default=0)
#     kurtosis_amp_counter_level_3 = models.IntegerField(default=0)
#     one_amp_repetition_level_3 = models.IntegerField(default=0)
#     one_amp_counter_level_3 = models.IntegerField(default=0)
#     two_amp_repetition_level_3 = models.IntegerField(default=0)
#     two_amp_counter_level_3 = models.IntegerField(default=0)
#     three_amp_repetition_level_3 = models.IntegerField(default=0)
#     three_amp_counter_level_3 = models.IntegerField(default=0)
#     four_amp_repetition_level_3 = models.IntegerField(default=0)
#     four_amp_counter_level_3 = models.IntegerField(default=0)
#     temp_amp_repetition_level_3 = models.IntegerField(default=0)
#     temp_amp_counter_level_3 = models.IntegerField(default=0)
#     axis = models.CharField(max_length=10, null=True, blank=True)
#     signal_type = models.CharField(max_length=50, null=True, blank=True)
#     domain = models.CharField(max_length=50, null=True, blank=True)
#     asset_id = models.CharField(max_length=150, null=True, blank=True)
#     creation_date=models.DateField(auto_now=True)

#     class Meta:
#         db_table = 'dynamic_threshold_counter_master'
#         # managed = False 




class AutoVelocityHarmonicsMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True)
    timestamp = models.DateTimeField(db_index=True)
    axis = models.CharField(max_length=10)
    data = models.JSONField(max_length=1000, null=True, blank=True)
    flag = models.BooleanField(default=False)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'auto_velocity_harmonics_master'
        # managed = False


class DiagnosticsValuesMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True)
    timestamp = models.DateTimeField(db_index=True)
    axis = models.CharField(max_length=10)
    signal_type = models.CharField(max_length=150, null=True, blank=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    one_amp = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    two_amp = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    three_amp = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    four_amp = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    five_amp = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    six_amp = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    seven_amp = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    eight_amp = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    nine_amp = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    ten_amp = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    four_to_seven_amp = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    flag = models.BooleanField(default=False)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'diagnostics_value_master'
        # managed = False


class DiagnosticsDynamicThresholdValuesMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True)
    axis = models.CharField(max_length=10)
    signal_type = models.CharField(max_length=150, null=True, blank=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    # attribute_type = models.CharField(max_length=150, null=True, blank=True)
    one_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    one_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    one_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    two_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    two_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    two_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    three_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    three_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    three_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    four_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    four_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    four_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    five_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    five_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    five_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    six_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    six_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    six_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    seven_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    seven_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    seven_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    eight_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    eight_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    eight_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    nine_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    nine_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    nine_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    ten_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    ten_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    ten_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    four_to_seven_amp_level_1 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    four_to_seven_amp_level_2 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    four_to_seven_amp_level_3 = models.DecimalField(max_digits=20, decimal_places=3, null=True, blank=True, default=0)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'diagnostics_dynamic_threshold_value_master'
        # managed = False


class DiagnosticThresholdCounterMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True)
    one_amp_repetition_level_1 = models.IntegerField(default=5)
    one_amp_counter_level_1 = models.IntegerField(default=0)
    two_amp_repetition_level_1 = models.IntegerField(default=5)
    two_amp_counter_level_1 = models.IntegerField(default=0)
    three_amp_repetition_level_1 = models.IntegerField(default=5)
    three_amp_counter_level_1 = models.IntegerField(default=0)
    four_amp_repetition_level_1 = models.IntegerField(default=5)
    four_amp_counter_level_1 = models.IntegerField(default=0)
    one_amp_repetition_level_2 = models.IntegerField(default=5)
    one_amp_counter_level_2 = models.IntegerField(default=0)
    two_amp_repetition_level_2 = models.IntegerField(default=5)
    two_amp_counter_level_2 = models.IntegerField(default=0)
    three_amp_repetition_level_2 = models.IntegerField(default=5)
    three_amp_counter_level_2 = models.IntegerField(default=0)
    four_amp_repetition_level_2 = models.IntegerField(default=5)
    four_amp_counter_level_2 = models.IntegerField(default=0)
    one_amp_repetition_level_3 = models.IntegerField(default=5)
    one_amp_counter_level_3 = models.IntegerField(default=0)
    two_amp_repetition_level_3 = models.IntegerField(default=5)
    two_amp_counter_level_3 = models.IntegerField(default=0)
    three_amp_repetition_level_3 = models.IntegerField(default=5)
    three_amp_counter_level_3 = models.IntegerField(default=0)
    four_amp_repetition_level_3 = models.IntegerField(default=5)
    four_amp_counter_level_3 = models.IntegerField(default=0)
    five_amp_repetition_level_1 = models.IntegerField(default=5)
    five_amp_counter_level_1 = models.IntegerField(default=0)
    six_amp_repetition_level_1 = models.IntegerField(default=5)
    six_amp_counter_level_1 = models.IntegerField(default=0)
    seven_amp_repetition_level_1 = models.IntegerField(default=5)
    seven_amp_counter_level_1 = models.IntegerField(default=0)
    eight_amp_repetition_level_1 = models.IntegerField(default=5)
    eight_amp_counter_level_1 = models.IntegerField(default=0)
    five_amp_repetition_level_2 = models.IntegerField(default=5)
    five_amp_counter_level_2 = models.IntegerField(default=0)
    six_amp_repetition_level_2 = models.IntegerField(default=5)
    six_amp_counter_level_2 = models.IntegerField(default=0)
    seven_amp_repetition_level_2 = models.IntegerField(default=5)
    seven_amp_counter_level_2 = models.IntegerField(default=0)
    eight_amp_repetition_level_2 = models.IntegerField(default=5)
    eight_amp_counter_level_2 = models.IntegerField(default=0)
    five_amp_repetition_level_3 = models.IntegerField(default=5)
    five_amp_counter_level_3 = models.IntegerField(default=0)
    six_amp_repetition_level_3 = models.IntegerField(default=5)
    six_amp_counter_level_3 = models.IntegerField(default=0)
    seven_amp_repetition_level_3 = models.IntegerField(default=5)
    seven_amp_counter_level_3 = models.IntegerField(default=0)
    eight_amp_repetition_level_3 = models.IntegerField(default=5)
    eight_amp_counter_level_3 = models.IntegerField(default=0)
    nine_amp_repetition_level_1 = models.IntegerField(default=5)
    nine_amp_counter_level_1 = models.IntegerField(default=0)
    ten_amp_repetition_level_1 = models.IntegerField(default=5)
    ten_amp_counter_level_1 = models.IntegerField(default=0)
    four_to_seven_amp_repetition_level_1 = models.IntegerField(default=5)
    four_to_seven_amp_counter_level_1 = models.IntegerField(default=0)
    nine_amp_repetition_level_2 = models.IntegerField(default=5)
    nine_amp_counter_level_2 = models.IntegerField(default=0)
    ten_amp_repetition_level_2 = models.IntegerField(default=5)
    ten_amp_counter_level_2 = models.IntegerField(default=0)
    four_to_seven_amp_repetition_level_2 = models.IntegerField(default=5)
    four_to_seven_amp_counter_level_2 = models.IntegerField(default=0)
    nine_amp_repetition_level_3 = models.IntegerField(default=5)
    nine_amp_counter_level_3 = models.IntegerField(default=0)
    ten_amp_repetition_level_3 = models.IntegerField(default=5)
    ten_amp_counter_level_3 = models.IntegerField(default=0)
    four_to_seven_amp_repetition_level_3 = models.IntegerField(default=5)
    four_to_seven_amp_counter_level_3 = models.IntegerField(default=0)
    axis = models.CharField(max_length=10, null=True, blank=True)
    signal_type = models.CharField(max_length=50, null=True, blank=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'diagnostic_threshold_counter_master'
        # managed = False 


class AutoCorrelationMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True)
    timestamp = models.DateTimeField(db_index=True)
    fs = models.IntegerField()
    no_of_samples = models.IntegerField( null=True, blank=True)
    data = ArrayField(models.CharField(max_length=50000)) 
    axis = models.CharField(max_length=10)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'auto_correlation_master'
        # managed = False

class GatewayMountMaster(models.Model):
    gateway_mac_id =  models.CharField(max_length=150)
    device_list = ArrayField(models.CharField(max_length=50000)) 
    location_id = models.CharField(max_length=150)
    org_id = models.CharField(max_length=150)
    creation_date=models.DateField(auto_now=True)
    last_update = models.DateTimeField(auto_now=True, null=True)
    class Meta:
        db_table = 'gateway_mount_master'
        # managed = False


class MagneticFluxStatMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True, db_index=True)
    timestamp = models.DateTimeField(null=True, blank=True, db_index=True)
    rms = models.DecimalField(max_digits=20, decimal_places=2)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    axis = models.CharField(max_length=20, default="a")
    flag = models.BooleanField(default=False)
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'magnetic_flux_stat_master'

class MagneticFluxSpectrumMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True, db_index=True)
    timestamp = models.DateTimeField(null=True, blank=True, db_index=True)
    twf_data = ArrayField(models.CharField(max_length=50000)) 
    spectrum_data = ArrayField(models.CharField(max_length=50000))
    frequency_data = ArrayField(models.CharField(max_length=50000))
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    axis = models.CharField(max_length=20, default="a")
    creation_date=models.DateField(auto_now=True)
    class Meta:
        db_table = 'magnetic_flux_spectrum_master'



class AssetUtilityMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True)
    data = models.JSONField(max_length=1000, null=True, blank=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateTimeField(auto_now=True)
    class Meta:
        db_table = 'asset_utility_master'


class AssetRunningVibrationValue(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True)
    stop_value = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    without_load_value = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    operating_value = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    creation_date=models.DateTimeField(auto_now=True)
    class Meta:
        db_table = 'asset_running_vibration_value_master'


class RuleBaseDiagnosticsMaster(models.Model):
    composite =  models.CharField(max_length=150, null=True, blank=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    faults_detected = models.JSONField(max_length=200, null=True, blank=True)
    creation_date=models.DateTimeField(auto_now=True)
    class Meta:
        db_table = 'rule_base_diagnostics_master'


class VelocityStatTimeOptimized(models.Model):
    composite = models.CharField(max_length=150, null=True, blank=True)
    timestamp = models.DateTimeField(db_index=True)

    rms_Axial = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    rms_Vertical = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    rms_Horizontal = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)

    peak_Axial = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    peak_Vertical = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    peak_Horizontal = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)

    peak_to_peak_Axial = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    peak_to_peak_Vertical = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    peak_to_peak_Horizontal = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)

    kurtosis_Axial = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    kurtosis_Vertical = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    kurtosis_Horizontal = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)

    flag = models.BooleanField(default=False)
    rms_only = models.BooleanField(default=False, db_index=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    mount_id = models.CharField(max_length=150, null=True, blank=True, db_index=True)
    creation_date = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'velocity_stat_time_optimized'
        # unique_together = (('timestamp', 'mount_id'),)


class AccelerationStatTimeOptimized(models.Model):
    composite = models.CharField(max_length=150, null=True, blank=True)
    timestamp = models.DateTimeField(db_index=True)

    rms_Axial = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    rms_Vertical = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    rms_Horizontal = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)

    peak_Axial = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    peak_Vertical = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    peak_Horizontal = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)

    peak_to_peak_Axial = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    peak_to_peak_Vertical = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    peak_to_peak_Horizontal = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)

    kurtosis_Axial = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    kurtosis_Vertical = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    kurtosis_Horizontal = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)

    flag = models.BooleanField(default=False)
    rms_only = models.BooleanField(default=False, db_index=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    mount_id = models.CharField(max_length=150, null=True, blank=True, db_index=True)
    creation_date = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'acceleration_stat_time_optimized'
        # unique_together = (('timestamp', 'mount_id'),)

class DisplacementStatTimeOptimized(models.Model):
    composite = models.CharField(max_length=150, null=True, blank=True)
    timestamp = models.DateTimeField(db_index=True)

    rms_Axial = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    rms_Vertical = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    rms_Horizontal = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)

    peak_Axial = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    peak_Vertical = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    peak_Horizontal = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)

    peak_to_peak_Axial = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    peak_to_peak_Vertical = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    peak_to_peak_Horizontal = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)

    kurtosis_Axial = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    kurtosis_Vertical = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    kurtosis_Horizontal = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)

    flag = models.BooleanField(default=False)
    rms_only = models.BooleanField(default=False, db_index=True)
    asset_id = models.CharField(max_length=150, null=True, blank=True)
    mount_id = models.CharField(max_length=150, null=True, blank=True, db_index=True)
    creation_date = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'displacement_stat_time_optimized'
        # unique_together = (('timestamp', 'mount_id'),)


class MigrationProgressAcc(models.Model):
    last_processed_id = models.BigIntegerField(default=0)  # Stores the last migrated row ID
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "migration_progress_acc"

class MigrationProgressVel(models.Model):
    last_processed_id = models.BigIntegerField(default=0)  # Stores the last migrated row ID
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "migration_progress_vel"

class MigrationProgressDis(models.Model):
    last_processed_id = models.BigIntegerField(default=0)  # Stores the last migrated row ID
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "migration_progress_dis"
