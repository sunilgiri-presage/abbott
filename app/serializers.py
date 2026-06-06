from rest_framework import serializers
from app.models import DeviceModelMaster,DeviceMountMaster,HardwareMaster,\
        Account,RawDataMaster,AccelerationTWFMaster,\
            AccelerationSpectrumMaster,VelocityTWFMaster,VelocitySpectrumMaster,\
                DisplacementTWFMaster,DisplacementSpectrumMaster,\
                    VelocityStatTimeMaster, AccelerationHarmonicsMaster,HardwareMaster,FirmwareMaster,\
                                SignalProcessingMaster,BearingFaultsMaster,\
                                    GearFaultsMaster,ACMotorFaultsMaster,\
                                        PumpFanFaultsMaster,EnvelopeTWFMaster,EnvelopeSpectrumMaster,\
                                            ThresholdValues, AccelerationStatTimeMaster, DisplacementStatTimeMaster,\
                                                AwsIotThingMaster,ThresholdCounterMaster, VelocityHarmonicsMaster, DisplacementHarmonicsMaster, TemperatureMaster,\
                                                    WiredSensorDataMaster, MobileAppKpiThreshold, EdgeCalculationParams, SpectrumChartDataMaster, KPIScoreMaster,\
                                                        BearingDetailMaster, AlarmHistoryMaster, SensorOrientationMaster, AssetHealthMaster, AssetHealthHistoryMaster,\
                                                            SensorPositionMaster, BearingFaultFrequenciesMaster, FrequencyDomainFeatuers, DynamicThresholdType, AcousticsMaster,\
                                                                AutoVelocityHarmonicsMaster, DiagnosticsValuesMaster, DiagnosticsDynamicThresholdValuesMaster, \
                                                                DiagnosticThresholdCounterMaster, AutoCorrelationMaster, GatewayMountMaster, SensorStatusNotifications, \
                                                                    AcousticsSpectrumMaster, MagneticFluxSpectrumMaster, MagneticFluxStatMaster, AssetUtilityMaster, AssetRunningVibrationValue, \
                                                                    RuleBaseDiagnosticsMaster, AlarmQueueMaster, AssetDiagnosticReportMaster



class DeviceModelMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceModelMaster
        fields = ['mount', 'composite_id','mac_id','asset_id','org_id', 'is_linked']

class DeviceMountMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceMountMaster
        fields = ['is_linked', "composite_id", 'point_name', 'mount_location', 'mount_type','mount_material',\
            'mount_direction', 'asset_id', 'org_id', 'mac_id', 'image', 'online']

# class HardwareMasterSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = HardwareMaster
#         fields = ['id', 'asset','mount', "composite_id",'part_od',\
#             'part_id','numberof_balls','bpfo','bpfi','bsf','ftf',\
#                 'asset_rpm','gear_ratio','gear_mesh_frequency','vane_pass_frequency','asset_id']

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



class RawDataMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawDataMaster
        fields = ["composite", 'timestamp', 'fs', 'no_of_samples', 'raw_data',\
            'axis','asset_id']
        
class PartialRawDataMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawDataMaster
        fields = ["id", "timestamp"]

class AccelerationTWFMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccelerationTWFMaster
        fields = ["composite", 'timestamp', 'fs', 'no_of_samples', 'data',\
            'axis','asset_id']

class AccelerationSpectrumMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccelerationSpectrumMaster
        fields = ["composite", 'timestamp', 'fs', 'no_of_samples', 'data',\
            'axis','asset_id','high_pass','low_pass','rpm']

class VelocityTWFMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = VelocityTWFMaster
        fields = ["composite", 'timestamp', 'fs', 'no_of_samples', 'data',\
            'axis','velocity_rms','asset_id']

class VelocitySpectrumMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = VelocitySpectrumMaster
        fields = ["composite", 'timestamp', 'fs', 'no_of_samples', 'data',\
            'axis','velocity_rms','asset_id','high_pass','low_pass','rpm']

class DisplacementTWFMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = DisplacementTWFMaster
        fields = ["composite", 'timestamp', 'fs', 'no_of_samples', 'data',\
            'axis','asset_id']
            
class DisplacementSpectrumMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = DisplacementSpectrumMaster
        fields = ["composite", 'timestamp', 'fs', 'no_of_samples', 'data',\
            'axis','asset_id','high_pass','low_pass','rpm']

class VelocityStatTimeMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = VelocityStatTimeMaster
        fields = ['composite', 'timestamp','rms','axis','peak','peak_to_peak','kurtosis','flag','asset_id', 'rms_only']

# class VelocityStatFreqMasterSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = VelocityStatFreqMaster
#         fields = ["composite", 'timestamp','rms','axis','peak','peak_to_peak','kurtosis','asset_id']


class AccelerationHarmonicsMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccelerationHarmonicsMaster
        fields = ["composite",'timestamp','axis','phase','one_amp','one_freq',\
            'two_amp','two_freq','three_amp','three_freq','four_amp','four_freq',\
                'five_amp','five_freq','flag','asset_id']

class VelocityHarmonicsMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = VelocityHarmonicsMaster
        fields = ["composite",'timestamp','axis','phase','half_amp','half_freq','one_amp','one_freq','one_half_amp','one_half_freq',\
            'two_amp','two_freq','two_half_amp','two_half_freq','three_amp','three_freq','three_half_amp',\
                'three_half_freq','four_amp','four_freq','four_half_amp','four_half_freq',\
                    'five_amp','five_freq','flag','asset_id']
        
class DisplacementHarmonicsMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = DisplacementHarmonicsMaster
        fields = ["composite",'timestamp','axis','phase','one_amp','one_freq',\
            'two_amp','two_freq','three_amp','three_freq','four_amp','four_freq',\
                'five_amp','five_freq','six_amp','six_freq','seven_amp','seven_freq',\
                    'eight_amp','eight_freq','nine_amp','nine_freq','ten_amp','ten_freq','flag','asset_id']

class HardwareMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = HardwareMaster
        fields = ['mount', "composite_id",'hardware_type','hardware_components','asset_id']

class FirmwareMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = FirmwareMaster
        fields = ['mount', "composite_id",'sampling_rate','no_of_samples','upload_time',\
            'sleep_time','asset_id', 'sensitivity', 'wired_rms_freq', 'sampling_rate_edge', 'no_of_samples_edge', 'bleRangeMode', 'acoustic_sampling_rate', 'rms_data_interval']

class EdgeCalculationParamsSerializer(serializers.ModelSerializer):
    class Meta:
        model = EdgeCalculationParams
        fields = ['mount', "composite_id",'sampling_rate','sleep_time','sensitivity','x_threshold','y_threshold',\
            'z_threshold','counter','edgeAlarmTimeOut', 'asset_id', "acc_rms_x", "acc_rms_y", \
                "acc_rms_z", "velocity_x", "velocity_y", "velocity_z", "temp", \
                    "acc_pp_x", "acc_pp_y", "acc_pp_z"]

class SignalProcessingMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = SignalProcessingMaster
        fields = ['mount', "composite_id",'high_pass','low_pass','vibration_twf','vib_fcutoff',\
            'vib_sampling_rate','vib_fmax','vib_no_of_samples','vib_freq_resolution',\
                'freq_spec_waterfall','acc_fcutoff','acc_sampling_rate','acc_fmax',\
                    'acc_no_of_samples','acc_freq_resolution','acc_rms','rpm',\
                        'battery_cut_off','battery_unstable_current','battery_unstable_samples',\
                            'battery_max_cycle','rul_power_coeff','rul_bound_limit','rul_ffa_rpm',\
                                'rul_ffa_ffr','rul_ffa_max_har_count','rul_ffa_min_accp_rpm',\
                                    'rul_ffa_max_accp_rpm','rul_learning_cond','sensitivity','asset_id']

class BearingFaultsMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = BearingFaultsMaster
        fields = ['mount', "composite_id",'fault','misalignment_unbalance','looseness','speed',\
            'bpfo','bpfi','bsf','ftf','fault_amp_thres','bpfo_coeff','bpfi_coeff','bsf_coeff',\
                    'misalig_amp_thres','unbalance_amp_thres','looseness_amp_thres','asset_id']

class GearFaultsMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = GearFaultsMaster
        fields = ['mount', "composite_id",'fault','misalignment_unbalance','looseness','constant_speed',\
            'no_of_gear_teeth','gear_ratio','gmp','misalig_amp_thres','unbalance_amp_thres',\
                'looseness_amp_thres','asset_id']

class ACMotorFaultsMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = ACMotorFaultsMaster
        fields = ['mount', "composite_id",'fault','misalignment_unbalance','looseness','line_freq',\
            'rotor_amp_thres','stator_amp_thres','misalig_amp_thres','unbalance_amp_thres',\
                'looseness_amp_thres','asset_id']

class PumpFanFaultsMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = PumpFanFaultsMaster
        fields = ['mount', "composite_id",'fault','misalignment_unbalance','looseness','vanes_no_lower',\
            'vanes_no_upper','vpf_amp_thres','vane_fault_amp_thres','misalig_amp_thres',\
                'unbalance_amp_thres','looseness_amp_thres','asset_id']

class EnvelopeTWFMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnvelopeTWFMaster
        fields = ["composite", 'timestamp', 'fs', 'no_of_samples','data',\
            'axis','asset_id']

class EnvelopeSpectrumMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = EnvelopeSpectrumMaster
        fields = ["composite", 'timestamp', 'fs', 'no_of_samples','data',\
            'axis','asset_id']


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
        fields = ["composite", 'timestamp','rms','axis','peak','peak_to_peak','kurtosis','flag','asset_id', 'rms_only']

# class AccelerationStatFreqMasterSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = AccelerationStatFreqMaster
#         fields = ["composite", 'timestamp','rms','axis','peak','peak_to_peak','kurtosis','asset_id']


class DisplacementStatTimeMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = DisplacementStatTimeMaster
        fields = ["composite", 'timestamp','rms','axis','peak','peak_to_peak','kurtosis','flag','asset_id', 'rms_only']

# class DisplacementStatFreqMasterSerializer(serializers.ModelSerializer):
#     class Meta:
#         model = DisplacementStatFreqMaster
#         fields = ["composite", 'timestamp','rms','axis','peak','peak_to_peak','kurtosis','asset_id']

class AwsIotThingMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = AwsIotThingMaster
        fields = ["composite", 'thingName', 'deviceShadow','thingArn','thingId','asset_id']

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
        fields = ["composite",'timestamp', 'temp','asset_id', 'axis', 'flag']

class AcousticsMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcousticsMaster
        fields = ["composite",'timestamp', 'acoustic_db', 'acoustic_rms', 'acoustic_rms_10k', 'acoustic_rms_20k', 'asset_id', 'axis', 'flag']

class WiredSensorDataMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = WiredSensorDataMaster
        fields = ["composite",'timestamp','x_rms','y_rms','z_rms','temp','asset_id']


class MobileAppKpiThresholdSerializer(serializers.ModelSerializer):
    class Meta:
        model = MobileAppKpiThreshold
        fields = ["composite", "asset_id", "v_rms_level_1", "v_rms_level_2", "v_rms_level_3", "a_envelope_level_1",\
                    "a_envelope_level_2", "a_envelope_level_3", "temp_level_1", "temp_level_2", "temp_level_3", "axis"]


class SpectrumChartDataMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpectrumChartDataMaster
        fields = ["composite", "asset_id", "timestamp", "acceleration", "velocity", "displacement"]


class KPIScoreMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = KPIScoreMaster
        fields = ["composite",'timestamp','rms','peak','peak_to_peak',\
                    'kurtosis','one_amp','two_amp','three_amp','four_amp','five_amp','six_amp',\
                        'seven_amp','eight_amp','nine_amp','ten_amp','axis','signal_type', 'asset_id']

class BearingDetailMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = BearingDetailMaster
        fields = ['mount','composite_id','bearing_number','bpfo','bpfi','bsf','ftf','asset_id']

class AlarmHistoryMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlarmHistoryMaster
        fields = ["composite", "timestamp", "signal_type", "trend_type", "axis", "priority", "sensor_location", "asset_id", "threshold_value", "observed_value"]


class AlarmQueueMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlarmQueueMaster
        fields = "__all__"


class AssetDiagnosticReportMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetDiagnosticReportMaster
        fields = "__all__"


class DiagnosticAlarmHistoryMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlarmHistoryMaster
        fields = ["composite", "timestamp", "signal_type", "trend_type", "axis", "priority", "sensor_location", "asset_id", "threshold_value", "observed_value", 'fault_flag']


class SensorOrientationMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = SensorOrientationMaster
        fields = ["position","x","y","z"]


class AssetHealthMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetHealthMaster
        fields = ["asset_id","org_id","status", "score"]

class AssetHealthHistoryMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetHealthHistoryMaster
        fields = ["asset_id","org_id","status"]

class AssetHealthHistoryMasterSerializerAll(serializers.ModelSerializer):
    class Meta:
        model = AssetHealthHistoryMaster
        fields = "__all__"


class SensorPositionMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = SensorPositionMaster
        fields = ["sensor_type","orientation"]


class BearingFaultFrequenciesMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = BearingFaultFrequenciesMaster
        fields = ["composite", "timestamp", "axis",\
                  "bpfo_amp", "bpfo_freq",\
                    "bpfi_amp", "bpfi_freq",\
                        "bsf_amp", "bsf_freq",\
                         "ftf_amp", "ftf_freq",\
                            "signal_type", "asset_id"]


class FrequencyDomainFeatuersSerializer(serializers.ModelSerializer):
    class Meta:
        model = FrequencyDomainFeatuers
        fields = ["composite","timestamp","ehnr","axis","asset_id"]

class DynamicThresholdTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DynamicThresholdType
        fields = ["asset_id","is_dynamic"]

class AutoVelocityHarmonicsMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = AutoVelocityHarmonicsMaster
        fields = [ "composite", "timestamp", "axis", "data", "asset_id"]

class DiagnosticsValuesMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiagnosticsValuesMaster
        fields = ["composite", "timestamp", "axis", "signal_type", "asset_id", "one_amp", "two_amp", "three_amp", "four_amp", "five_amp", "six_amp", \
                  "seven_amp", "eight_amp", "nine_amp", "ten_amp", "four_to_seven_amp"]

class DiagnosticsDynamicThresholdValuesMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiagnosticsDynamicThresholdValuesMaster
        fields = ["composite", "axis", "signal_type", "asset_id", "one_amp_level_1", "one_amp_level_2", "one_amp_level_3", \
                  "two_amp_level_1", "two_amp_level_2", "two_amp_level_3" , "three_amp_level_1", "three_amp_level_2", "three_amp_level_3", \
                    "four_amp_level_1", "four_amp_level_2", "four_amp_level_3", "five_amp_level_1", "five_amp_level_2", "five_amp_level_3", \
                        "six_amp_level_1", "six_amp_level_2", "six_amp_level_3", "seven_amp_level_1", "seven_amp_level_2", "seven_amp_level_3", \
                            "eight_amp_level_1", "eight_amp_level_2", "eight_amp_level_3", "nine_amp_level_1", "nine_amp_level_2", "nine_amp_level_3", \
                                "ten_amp_level_1", "ten_amp_level_2", "ten_amp_level_3", "four_to_seven_amp_level_1", "four_to_seven_amp_level_2", \
                                    "four_to_seven_amp_level_3"]



class DiagnosticThresholdCounterMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiagnosticThresholdCounterMaster
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
                                                                "axis","signal_type","domain","asset_id", "rms_amp_repetition_level_1_timestamp", "peak_amp_repetition_level_1_timestamp", "peak_to_peak_amp_repetition_level_1_timestamp", \
                                                                    "kurtosis_amp_repetition_level_1_timestamp", "one_amp_repetition_level_1_timestamp", "two_amp_repetition_level_1_timestamp", "three_amp_repetition_level_1_timestamp", \
                                                                        "four_amp_repetition_level_1_timestamp", "temp_amp_repetition_level_1_timestamp", "rms_amp_repetition_level_2_timestamp", "peak_amp_repetition_level_2_timestamp", \
                                                                            "peak_to_peak_amp_repetition_level_2_timestamp", "kurtosis_amp_repetition_level_2_timestamp", "one_amp_repetition_level_2_timestamp", "two_amp_repetition_level_2_timestamp", \
                                                                                "three_amp_repetition_level_2_timestamp", "four_amp_repetition_level_2_timestamp", "temp_amp_repetition_level_2_timestamp", "rms_amp_repetition_level_3_timestamp", \
                                                                                    "peak_amp_repetition_level_3_timestamp", "peak_to_peak_amp_repetition_level_3_timestamp", "kurtosis_amp_repetition_level_3_timestamp", \
                                                                                        "one_amp_repetition_level_3_timestamp", "two_amp_repetition_level_3_timestamp", "three_amp_repetition_level_3_timestamp", "four_amp_repetition_level_3_timestamp", \
                                                                                            "temp_amp_repetition_level_3_timestamp"
        ]


class AutoCorrelationMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = AutoCorrelationMaster
        fields = ["composite", 'timestamp', 'fs', 'no_of_samples', 'data', 'axis','asset_id']


class GatewayMountMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = GatewayMountMaster
        fields = ["gateway_mac_id", "device_list", "location_id", "org_id"]

class SensorStatusNotificationsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SensorStatusNotifications
        fields = ["mount","composite_id", "asset_id"]


class AcousticsSpectrumMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcousticsSpectrumMaster
        fields = ["composite", 'timestamp', 'twf_data', 'spectrum_data', 'spectrum_data_10k', 'spectrum_data_20k', \
                  'frequency_data', 'frequency_data_10k', 'frequency_data_20k', 'asset_id','axis']


class MagneticFluxSpectrumMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = MagneticFluxSpectrumMaster
        fields = ["composite", 'timestamp', 'twf_data', 'spectrum_data', 'frequency_data', 'asset_id','axis']


class MagneticFluxStatMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = MagneticFluxStatMaster
        fields = ["composite", 'timestamp', 'rms', 'asset_id','axis']


class AssetUtilityMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetUtilityMaster
        fields = ["composite", 'data','asset_id']

class AssetRunningVibrationValueSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetRunningVibrationValue
        fields = ["composite", 'stop_value', 'without_load_value', 'operating_value','asset_id']

class RuleBaseDiagnosticsMasterSerializer(serializers.ModelSerializer):
    class Meta:
        model = RuleBaseDiagnosticsMaster
        fields = ["composite",'asset_id', 'faults_detected']


