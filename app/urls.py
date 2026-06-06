from django.urls import path
from app.account import views as account_views
from app.dashboard import views as dashboard_views
from app.config import views as config_views
from app.pdfGenerator import views as pdf_views
from app.dbUpdate import views as db_update_views
from app.playground import views as playground_views
from app import cron as cron_views
from app.thresholdFunctions import thresholdFunctions
from app.cron import CalculateAssetHealthScore, CalculateThresholdForDiagnostics, CalculateAssetHealthScoreManually, calculateAutoDiagnostics, checkSensorLiveStatus, CalculateAssetUtilityScore, DumpCounterDataToDatabase
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from app.celeryFolder import views as celery_views

urlpatterns = [

    # ************************* Account urls path *************************

    path('register_admin/', account_views.admin_registration_view),
    path('register/', account_views.customer_registration_view),
    path('login/', account_views.login),
    path('forgot_password/', account_views.forgot_password),


    # ************************* dynamic threshold urls path *************************
    path('set_dynamic_threshold/', thresholdFunctions.CheckDynamicThreshold.as_view(), name='set_dynamic_threshold'),
    path('auto_diagnostics/', calculateAutoDiagnostics, name='auto_diagnostics'),
    path('asset_diagnostics_v4/', cron_views.AssetDiagnosticsV4.as_view(), name='asset_diagnostics_v4'),
    path('test_asset_diagnostics_alarm_flow/', cron_views.TestAssetDiagnosticsAlarmFlow.as_view(), name='test_asset_diagnostics_alarm_flow'),


    # ************************* checkThresholdCounterAPI *************************
    path('check_threshold_counterAPI/', thresholdFunctions.checkThresholdCounterAPI, name='check_threshold_counterAPI'),
   
   
    path('check_sensor_live_status/', checkSensorLiveStatus, name='set_dynamic_threshold'),

    # ************************* Asset Utility api *************************
    path('calculate_asset_utility/', CalculateAssetUtilityScore, name='calculate_asset_utility'),


    # # ************************* dynamic threshold for diagnostics *************************
    # path('set_dynamic_threshold_for_diagnostics/', CalculateThresholdForDiagnostics.as_view(), name='set_dynamic_threshold_for_diagnostics'),

    # ************************* dynamic threshold for diagnostics *************************
    path('dump_counter_data/', DumpCounterDataToDatabase, name='dump_counter_data'),


    # # ************************* dynamic threshold counter for diagnostics *************************
    # path('set_dynamic_threshold_counter_for_diagnostics/', diagnostics.CalculateCounterForDiagnostics.as_view(), name='set_dynamic_threshold_counter_for_diagnostics'),


    # # ************************* dynamic threshold counter check for diagnostics *************************
    # path('check_dynamic_threshold_counter_for_diagnostics/', diagnostics.checkDiagnosticThresholdCounter.as_view(), name='set_dynamic_threshold_counter_for_diagnostics'),


    # ************************* asset health score urls path *************************
    # path('calculate_asset_score/', CalculateAssetHealthScore.as_view(), name='calculate_asset_score'),
    path('calculate_asset_score_manually/', CalculateAssetHealthScoreManually.as_view(), name = 'calculate_asset_score_manually'),
    


    # ************************* pdf urls path *************************
    path('generateAssetReport/', pdf_views.generate_asset_report, name='generate_pdf'),
    path('generateLocationReport/', pdf_views.generate_location_report, name='generate_pdf'),
    

    # ************************* database update urls path *************************
    path('get_mount_ids/', db_update_views.getMountIds),


    # ************************* playground urls path *************************
    path('processEnvelopeSpectrum/', playground_views.process_envelope_spectrum_data, name='process_envelope'),
    path('play_screen_api/', playground_views.PlayScreenAPI, name='process_envelope'),
    path('get_config/', playground_views.GetConfig, name='get_config'),


    # ************************* Config urls path *************************

    path('devices/', config_views.device_list),
    path('devices_update/', config_views.devices_update),
    # path('add_devices/', config_views.add_devices),
    path('check_device/', config_views.check_device),
    path('device_config/', config_views.device_config),
    path('get_device_config/', config_views.get_device_config),
    path('hardwares/', config_views.hardware_list),
    path('hardwares/<int:pk>/', config_views.hardware_detail),
    path('firmware_config/', config_views.get_firmware_config),
    path('add_sensor/', config_views.add_sensor),
    path('asset_count/', config_views.GetAssetCount),
    path('getDeviceConfigurations/', config_views.GetSensorConfigurations),
    path('updateDeviceConfigurations/', config_views.UpdateSensorConfigurations),
    path('endPointApi/', config_views.EndPointAPI),
    path('deleteEndPointApi/<pk>', config_views.DeleteEndPointAPI),
    path('getAllEndPoints/', config_views.getAllEndPoints),
    path('getAllEndPointsMobile/', config_views.getAllEndPointsMobile),
    path('sensor_orientation/', config_views.SensorOrientation),
    path('get_rms_data_portable/', config_views.GetRMSDataPortable),
    path('changeDevice/', config_views.unmapMapSensor),
    path('updateEndPointImage/', config_views.updateEndPointImage),
    path('update_endpoint/', config_views.updateEndPointName),
    path('save_gateway_devices/', config_views.SaveGatewayDevices.as_view(), name = 'save_gateway_devices'),
    path('save_asset_running_vibration/', config_views.SaveAssetRunningVibrationValue.as_view()),
    

    # ************************* Dashboard urls path *************************

    path('raw_data/', dashboard_views.raw_data_list),
    path('raw_data_portable/', dashboard_views.savePortableSensorData),
    path('device_raw_data/', dashboard_views.device_raw_data),
    path('acceleration_amplitude/', dashboard_views.acceleration_amplitude_list),
    path('acceleration_frequency/', dashboard_views.acceleration_frequency_list),
    path('get_acceleration_twf/', dashboard_views.get_acceleration_twf),
    path('get_acceleration_spectrum/', dashboard_views.get_acceleration_spectrum),
    path('get_velocity_twf/', dashboard_views.get_velocity_twf),
    path('get_velocity_spectrum/', dashboard_views.get_velocity_spectrum),
    path('displacement_amplitude/', dashboard_views.displacement_amplitude_list),
    path('displacement_frequency/', dashboard_views.displacement_frequency_list),
    path('get_displacement_twf/', dashboard_views.get_displacement_twf),
    path('get_displacement_spectrum/', dashboard_views.get_displacement_spectrum),
    path('velocity_rms/', dashboard_views.velocity_rms_list),
    path('get_function_trend_data/', dashboard_views.getFunctionTrendData),
    # path('get_function_trend_data/', dashboard_views.getFunctionTrendData),
    path('harmonics/', dashboard_views.harmonics_list),
    path('get_harmonics_data/', dashboard_views.get_harmonics_data),
    path('harmonics_filter_data/', dashboard_views.harmonics_filter_data),
    path('get_timestamp/', dashboard_views.get_timestamp),
    path('get_device_location/', dashboard_views.get_device_location),
    path('envelope_amplitude/', dashboard_views.envelope_amplitude_list),
    path('envelope_frequency/', dashboard_views.envelope_frequency_list),
    path('get_envelope_twf/', dashboard_views.get_envelope_twf),
    path('get_envelope_spectrum/', dashboard_views.get_envelope_spectrum),
    path('testApi/', dashboard_views.testApi),
    path('get_devices/', dashboard_views.getDevice),
    path('get_alarm_plot_data_time/', dashboard_views.getPlotDataTime),
    path('get_alarm_plot_data_freq/', dashboard_views.getPlotDataFreq),
    path('get_alarm_plot_data_temp/', dashboard_views.getPlotDataTemp),
    path('threshold/', dashboard_views.thresholdValues),
    path('get_threshold/', dashboard_views.GetThresholdData),
    path('get_temp/', dashboard_views.GetTempData),
    path('get_acoustic/', dashboard_views.GetAcousticData),
    path('wired_sensor_data/', dashboard_views.SaveWiredSensorData),
    path('ble_rms_sensor_data/', dashboard_views.SaveBleRMSSensorData),
    path('get_wired_sensor_data/', dashboard_views.GetWiredSensorData),
    path('get_kpi_value_mobile/', dashboard_views.GetKpiValueMobile),
    path("save_threshold_mobile_kpi/", dashboard_views.SaveThresholdValues),
    path("get_threshold_mobile_kpi/", dashboard_views.GetThresholdValuesMobile),
    path("get_bearing_fault_frequencies_data/", dashboard_views.GetBearingFaultFrequenciesData),
    path("get_endpoint_details_report/", dashboard_views.getEndpointDetailsReport),
    path("get_endpoint_data_report/", dashboard_views.getEndpointDataReport),
    path("get_waterfall_data/", dashboard_views.getWaterfallData),
    path("get_alarm_history_data/", dashboard_views.getAlarmHistoryData),
    path("get_alarm_history_summary/", dashboard_views.getAlarmHistorySummary),
    path("get_asset_health_kpi_summary/", dashboard_views.getAssetHealthKPISummary),
    path("asset_health_status/", dashboard_views.AssetHealthAPI),
    path("asset_health_status_summary/", dashboard_views.getAssetHealthHistory),
    path("get_asset_health_location_api/", dashboard_views.getAssetHealthStatus),
    path("single_asset_health_history/", dashboard_views.getSingleAssetHealthHistory),
    path("get_asset_against_health_status/", dashboard_views.getAssetAgainstHealthStatus),
    path("get_bearing_fault_frequencies/", dashboard_views.GetBearingFaultFrequencies),
    path("get_bearing_fault_frequencies_trend/", dashboard_views.GetBearingFaultFrequenciesTrend),
    path("get_harmonic_trend/", dashboard_views.GetHarmonicTrend),
    path("get_ehnr_trend/", dashboard_views.GetEHNRTrend),
    path("get_analysis_trend/", dashboard_views.GetAnalysisTrend),
    path("get_asset_monthly_trend/", dashboard_views.GetAssetMonthlyTrend),
    path("get_raw_data/", dashboard_views.GetRawData),
    path("envelope_play/", dashboard_views.AccelerationEnvelopePlay),
    path("asset_report_trend/", dashboard_views.AssetReportTrend),
    # path("save_rms_data/", dashboard_views.SaveRMSData.as_view()),
    path('download_raw_data/<param1>/<param2>/', dashboard_views.get_raw_data.as_view(), name = 'get_raw_data'),
    path('auto_threshold/<param1>/', dashboard_views.AutoThreshold.as_view(), name = 'auto_threshold'),
    path('get_auto_correlation_data/', dashboard_views.get_auto_correlation),
    path('get_asset_rms_temp_kpi/', dashboard_views.GetAssetRmsTempKpi.as_view(), name = 'get_asset_rms_temp_kpi'),
    path('get_devices_gateway/', dashboard_views.getGatewayDeviceList),
    path('get_gateway_list/', dashboard_views.getGatewayList),
    path('get_acoustic_spectrum/', dashboard_views.getAcousticSpectrum),
    path('get_magnetic_rms_data/', dashboard_views.GetMagnetisRMSData),
    path('get_magnetic_spectrum/', dashboard_views.getMagneticSpectrum),
    path('get_endpoint_kpis/', dashboard_views.getEndpointKPIS),
    path('get_asset_utility/', dashboard_views.getAssetUtility),
    path('get_acceleration_data/', dashboard_views.getAccelerationData),
    path('get_velocity_data/', dashboard_views.getVelocityData),
    path('get_displacement_data/', dashboard_views.getDisplacementData),
    path('get_envelope_data/', dashboard_views.getEnvelopeData),
    # path('process_rms_batch/', cron_views.process_rms_batch),
    



    # ************************* Celery urls path *************************
    path('without_celery/', celery_views.WithoutCelery),
    path('with_celery/', celery_views.WithCelery),


    # ************************* Floor map urls path *************************
    path('floor_map_health_kpi/', dashboard_views.FloorMapHealthKpi),
    
]
