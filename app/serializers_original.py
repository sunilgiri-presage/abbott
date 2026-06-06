from rest_framework import serializers
from app.models import CompanyMaster,LocationMaster,AreaMaster,EquipmentMaster,\
    AssetMaster,AssetImage,DeviceModelMaster,DeviceMountMaster,HardwareMaster,\
        RoleMaster,Account,RawDataMaster,AccelerationAmplitudeMaster,\
            AccelerationFrequencyMaster,VelocityAmplitudeMaster,VelocityFrequencyMaster,\
                DisplacementAmplitudeMaster,DisplacementFrequencyMaster,\
                    VelocityStatTimeMaster,DeviceHealthStatus,\
                        ISOFlagsMaster,TimeWaveMaster,FrequencyWaveMaster,\
                            AccelerationHarmonicsMaster,HardwareMaster,FirmwareMaster,\
                                SignalProcessingMaster,BearingFaultsMaster,\
                                    GearFaultsMaster,ACMotorFaultsMaster,\
                                        PumpFanFaultsMaster,EnvelopeAmplitudeMaster,EnvelopeFrequencyMaster,\
                                            AssetTimestampData,AssetHealthScore,ThresholdValues, AccelerationStatTimeMaster, DisplacementStatTimeMaster,\
                                                AwsIotThingMaster,ThresholdCounterMaster, VelocityHarmonicsMaster, DisplacementHarmonicsMaster, TemperatureMaster,\
                                                    WiredSensorDataMaster



class CompanyMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyMaster
        fields = ['id', 'comp_name', 'contact_number', 'company_description', 'comp_id_cmms']

class LocationMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = LocationMaster
        fields = ['id', 'company', 'location_name', 'location','address','location_description','cmms_org']

class AreaMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = AreaMaster
        fields = ['id', 'location', 'area_name', 'area_type','area_description','cmms_org']

class EquipmentMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = EquipmentMaster
        fields = ['id', 'area', 'equipment_name', 'equipment_type','equipment_class',\
            'equipment_description','cmms_org']

class AssetMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetMaster
        fields = ['id', 'equipment', 'asset_name', 'asset_type','asset_class_type',\
            'asset_description','cmms_org']

class AssetImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetImage
        fields = ['id', 'asset', 'file', 'cmms_org']

class DeviceModelMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceModelMaster
        fields = ['device_key','device_value','asset_id','cmms_org']

class DeviceMountMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceMountMaster
        fields = ['device', 'mount_location', 'mount_type','mount_material',\
            'mount_direction']

class HardwareMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = HardwareMaster
        fields = ['id', 'asset', 'device','part_od',\
            'part_id','numberof_balls','bpfo','bpfi','bsf','ftf',\
                'asset_rpm','gear_ratio','gear_mesh_frequency','vane_pass_frequency','cmms_org']

class RoleMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoleMaster
        fields = ['id', 'name', 'cmms_org']


class AdminRegistrationSerializer(serializers.ModelSerializer):

	class Meta:
		model = Account
		fields = ['email', 'password']
		extra_kwargs = {
				'password': {'write_only': True},
		}	


	def	save(self):
		password = self.validated_data['password']
		account = Account.objects.create_superuser(
					email=self.validated_data['email'],
					username=self.validated_data['email'],
                    password=self.validated_data['password']
				)
		account.set_password(password)
		account.save()
		return account

class CustomerRegistrationSerializer(serializers.ModelSerializer):

    class Meta:
        model = Account
        fields = ['email', 'password']
        extra_kwargs = {
                'password': {'write_only': True},
        }	


    def	save(self):

        account = Account(
                    email=self.validated_data['email'],
                    username=self.validated_data['email']
                )
        password = self.validated_data['password']
        account.set_password(password)
        account.save()
        return account

class RawDataMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawDataMaster
        fields = ['device', 'timestamp', 'fs', 'no_of_samples', 'raw_data',\
            'axis','cmms_org']

class AccelerationAmplitudeMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccelerationAmplitudeMaster
        fields = ['device', 'timestamp', 'fs', 'no_of_samples', 'data',\
            'axis','cmms_org']

class AccelerationFrequencyMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccelerationFrequencyMaster
        fields = ['device', 'timestamp', 'fs', 'no_of_samples', 'data',\
            'axis','cmms_org']

class VelocityAmplitudeMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = VelocityAmplitudeMaster
        fields = ['device', 'timestamp', 'fs', 'no_of_samples', 'data',\
            'axis','velocity_rms','cmms_org']

class VelocityFrequencyMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = VelocityFrequencyMaster
        fields = ['device', 'timestamp', 'fs', 'no_of_samples', 'data',\
            'axis','velocity_rms','cmms_org']

class DisplacementAmplitudeMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = DisplacementAmplitudeMaster
        fields = ['device', 'timestamp', 'fs', 'no_of_samples', 'data',\
            'axis','cmms_org']
            
class DisplacementFrequencyMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = DisplacementFrequencyMaster
        fields = ['device', 'timestamp', 'fs', 'no_of_samples', 'data',\
            'axis','cmms_org']

class VelocityStatTimeMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = VelocityStatTimeMaster
        fields = ['device', 'timestamp','rms','axis','peak','peak_to_peak','kurtosis','flag','cmms_org']

# class VelocityStatFreqMasterSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = VelocityStatFreqMaster
#         fields = ['device', 'timestamp','rms','axis','peak','peak_to_peak','kurtosis','org_id']

class ISOFlagsMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = ISOFlagsMaster
        fields = ['min_range_inch','max_range_inch','min_range_mm','max_range_mm','flag','class_type']

class DeviceHealthStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceHealthStatus
        fields = ['device','timestamp','data','axis','flag','device_score','class_type']

class TimeWaveMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeWaveMaster
        fields = ['device','data','cmms_org']

class FrequencyWaveMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = FrequencyWaveMaster
        fields = ['device','data','cmms_org']

class AccelerationHarmonicsMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccelerationHarmonicsMaster
        fields = ['device','timestamp','axis','phase','one_amp','one_freq',\
            'two_amp','two_freq','three_amp','three_freq','four_amp','four_freq',\
                'five_amp','five_freq','six_amp','six_freq','seven_amp','seven_freq',\
                    'eight_amp','eight_freq','nine_amp','nine_freq','ten_amp','ten_freq','flag','cmms_org']

class VelocityHarmonicsMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = VelocityHarmonicsMaster
        fields = ['device','timestamp','axis','phase','one_amp','one_freq',\
            'two_amp','two_freq','three_amp','three_freq','four_amp','four_freq',\
                'five_amp','five_freq','six_amp','six_freq','seven_amp','seven_freq',\
                    'eight_amp','eight_freq','nine_amp','nine_freq','ten_amp','ten_freq','flag','cmms_org']

class DisplacementHarmonicsMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = DisplacementHarmonicsMaster
        fields = ['device','timestamp','axis','phase','one_amp','one_freq',\
            'two_amp','two_freq','three_amp','three_freq','four_amp','four_freq',\
                'five_amp','five_freq','six_amp','six_freq','seven_amp','seven_freq',\
                    'eight_amp','eight_freq','nine_amp','nine_freq','ten_amp','ten_freq','flag','cmms_org']

class HardwareMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = HardwareMaster
        fields = ['device','hardware_type','hardware_components','cmms_org']

class FirmwareMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = FirmwareMaster
        fields = ['device','firmware_version','no_of_samples','no_of_files','upload_time',\
            'sleep_time','machine_running','cmms_org']

class SignalProcessingMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = SignalProcessingMaster
        fields = ['device','vibration_rms','overall_rms','vibration_twf','vib_fcutoff',\
            'vib_sampling_rate','vib_fmax','vib_no_of_samples','vib_freq_resolution',\
                'freq_spec_waterfall','acc_fcutoff','acc_sampling_rate','acc_fmax',\
                    'acc_no_of_samples','acc_freq_resolution','acc_rms','temperature',\
                        'battery_cut_off','battery_unstable_current','battery_unstable_samples',\
                            'battery_max_cycle','rul_power_coeff','rul_bound_limit','rul_ffa_rpm',\
                                'rul_ffa_ffr','rul_ffa_max_har_count','rul_ffa_min_accp_rpm',\
                                    'rul_ffa_max_accp_rpm','rul_learning_cond','sensitivity','cmms_org']

class BearingFaultsMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = BearingFaultsMaster
        fields = ['device','fault','misalignment_unbalance','looseness','speed',\
            'bpfo','bpfi','bsf','ftf','fault_amp_thres','bpfo_coeff','bpfi_coeff','bsf_coeff',\
                    'misalig_amp_thres','unbalance_amp_thres','looseness_amp_thres','cmms_org']

class GearFaultsMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = GearFaultsMaster
        fields = ['device','fault','misalignment_unbalance','looseness','constant_speed',\
            'no_of_gear_teeth','gear_ratio','gmp','misalig_amp_thres','unbalance_amp_thres',\
                'looseness_amp_thres','cmms_org']

class ACMotorFaultsMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = ACMotorFaultsMaster
        fields = ['device','fault','misalignment_unbalance','looseness','line_freq',\
            'rotor_amp_thres','stator_amp_thres','misalig_amp_thres','unbalance_amp_thres',\
                'looseness_amp_thres','cmms_org']

class PumpFanFaultsMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = PumpFanFaultsMaster
        fields = ['device','fault','misalignment_unbalance','looseness','vanes_no_lower',\
            'vanes_no_upper','vpf_amp_thres','vane_fault_amp_thres','misalig_amp_thres',\
                'unbalance_amp_thres','looseness_amp_thres','cmms_org']

class EnvelopeAmplitudeMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnvelopeAmplitudeMaster
        fields = ['device', 'timestamp', 'fs', 'no_of_samples','data',\
            'axis','cmms_org']

class EnvelopeFrequencyMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnvelopeFrequencyMaster
        fields = ['device', 'timestamp', 'fs', 'no_of_samples','data',\
            'axis','cmms_org']

class AssetTimestampDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetTimestampData
        fields = ['asset','timestamp','flag','cmms_org']

class AssetHealthScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetHealthScore
        fields = ['asset','timestamp','score','fault_mode','cmms_org']

class ThresholdValuesSerializer(serializers.ModelSerializer):
    class Meta:
        model = ThresholdValues
        fields = ["composite",
                    'rms_amp_level_1','peak_amp_level_1','peak_to_peak_amp_level_1','kurtosis_amp_level_1','one_amp_level_1','two_amp_level_1','three_amp_level_1','four_amp_level_1','temp_amp_level_1',\
                        'rms_amp_level_2','peak_amp_level_2','peak_to_peak_amp_level_2','kurtosis_amp_level_2','one_amp_level_2','two_amp_level_2','three_amp_level_2','four_amp_level_2','temp_amp_level_2',\
                            'rms_amp_level_3','peak_amp_level_3','peak_to_peak_amp_level_3','kurtosis_amp_level_3','one_amp_level_3','two_amp_level_3','three_amp_level_3','four_amp_level_3','temp_amp_level_3',\
                                'axis','signal_type','domain', 'asset_id']

class AccelerationStatTimeMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccelerationStatTimeMaster
        fields = ['device', 'timestamp','rms','axis','peak','peak_to_peak','kurtosis','flag','cmms_org']

# class AccelerationStatFreqMasterSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = AccelerationStatFreqMaster
#         fields = ['device', 'timestamp','rms','axis','peak','peak_to_peak','kurtosis','org_id']


class DisplacementStatTimeMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = DisplacementStatTimeMaster
        fields = ['device', 'timestamp','rms','axis','peak','peak_to_peak','kurtosis','flag','cmms_org']

# class DisplacementStatFreqMasterSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = DisplacementStatFreqMaster
#         fields = ['device', 'timestamp','rms','axis','peak','peak_to_peak','kurtosis','org_id']

class AwsIotThingMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = AwsIotThingMaster
        fields = ['device', 'thingName', 'deviceShadow','thingArn','thingId','cmms_org']

class ThresholdCounterMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = ThresholdCounterMaster
        fields = ["composite",\
                    "rms_amp_repetition_level_1","rms_amp_counter_level_1","peak_amp_repetition_level_1","peak_amp_counter_level_1","peak_to_peak_amp_repetition_level_1","peak_to_peak_amp_counter_level_1",\
                        "kurtosis_amp_repetition_level_1","kurtosis_amp_counter_level_1","one_amp_repetition_level_1","one_amp_counter_level_1","two_amp_repetition_level_1","two_amp_counter_level_1",\
                            "three_amp_repetition_level_1","three_amp_counter_level_1","four_amp_repetition_level_1","four_amp_counter_level_1","temp_amp_repetition_level_1","temp_amp_counter_level_1",\
                                    "rms_amp_repetition_level_2","rms_amp_counter_level_2","peak_amp_repetition_level_2","peak_amp_counter_level_2","peak_to_peak_amp_repetition_level_2","peak_to_peak_amp_counter_level_2",\
                                        "kurtosis_amp_repetition_level_2","kurtosis_amp_counter_level_2","one_amp_repetition_level_2","one_amp_counter_level_2","two_amp_repetition_level_2","two_amp_counter_level_2",\
                                            "three_amp_repetition_level_2","three_amp_counter_level_2","four_amp_repetition_level_2","four_amp_counter_level_2","temp_amp_repetition_level_2","temp_amp_counter_level_2",\
                                                    "rms_amp_repetition_level_3","rms_amp_counter_level_3","peak_amp_repetition_level_3","peak_amp_counter_level_3","peak_to_peak_amp_repetition_level_3","peak_to_peak_amp_counter_level_3",\
                                                        "kurtosis_amp_repetition_level_3","kurtosis_amp_counter_level_3","one_amp_repetition_level_3","one_amp_counter_level_3","two_amp_repetition_level_3","two_amp_counter_level_3",\
                                                            "three_amp_repetition_level_3","three_amp_counter_level_3","four_amp_repetition_level_3","four_amp_counter_level_3","temp_amp_repetition_level_3","temp_amp_counter_level_3",\
                                                                "axis","signal_type","domain","asset_id",
        ]


class TemperatureMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemperatureMaster
        fields = ['device','timestamp', 'temp','cmms_org']


class WiredSensorDataMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = WiredSensorDataMaster
        fields = ['device','timestamp','x_rms','y_rms','z_rms','temp','cmms_org']

