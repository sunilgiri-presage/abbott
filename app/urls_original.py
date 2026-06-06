from django.urls import path
from app.account import views as account_views
from app.dashboard import views as dashboard_views
from app.config import views as config_views
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny

urlpatterns = [

    # ************************* Account urls path *****************

    path('register_admin/', account_views.admin_registration_view),
    path('register/', account_views.customer_registration_view),
    path('login/', account_views.login),
    path('forgot_password/', account_views.forgot_password),

    # ************************* Config urls path *****************

    path('companies/', config_views.company_list),
    path('companies/<int:pk>/', config_views.company_detail),
    path('locations/', config_views.location_list),
    path('locations/<int:pk>/', config_views.location_detail),
    path('areas/', config_views.area_list),
    path('areas/<int:pk>/', config_views.area_detail),
    path('equipments/', config_views.equipment_list),
    path('equipments/<int:pk>/', config_views.equipment_detail),
    path('assets/', config_views.asset_list),
    path('asset_image/', config_views.AssetImage.as_view()),
    path('assets/<int:pk>/', config_views.asset_detail),
    path('devices/', config_views.device_list),
    path('devices_update/', config_views.devices_update),
    path('add_devices/', config_views.add_devices),
    path('check_device/', config_views.check_device),
    path('device_config/', config_views.device_config),
    path('get_device_config/', config_views.get_device_config),
    path('hardwares/', config_views.hardware_list),
    path('hardwares/<int:pk>/', config_views.hardware_detail),
    path('roles/', config_views.role_list),
    path('roles/<int:pk>/', config_views.role_detail),
    path('iso_flags/', config_views.iso_flags_list),
    path('timewave_data/', config_views.timewave_list),
    path('frequencywave_data/', config_views.frequencywave_list),
    path('firmware_config/', config_views.get_firmware_config),
    path('add_sensor/', config_views.add_sensor),
    

    # ************************* Dashboard urls path *****************

    path('area_data/', dashboard_views.area_data),
    path('equipment_list/', dashboard_views.equipment_list),
    path('asset_data/', dashboard_views.asset_data),
    path('raw_data/', dashboard_views.raw_data_list),
    path('device_raw_data/<int:device_id>/', dashboard_views.device_raw_data),
    path('acceleration_amplitude/', dashboard_views.acceleration_amplitude_list),
    path('acceleration_frequency/', dashboard_views.acceleration_frequency_list),
    path('get_acceleration_amplitude/', dashboard_views.get_acceleration_amplitude),
    path('get_acceleration_frequency/', dashboard_views.get_acceleration_frequency),
    path('velocity_amplitude/', dashboard_views.velocity_amplitude_list),
    path('velocity_frequency/', dashboard_views.velocity_frequency_list),
    path('get_velocity_amplitude/', dashboard_views.get_velocity_amplitude),
    path('get_velocity_frequency/', dashboard_views.get_velocity_frequency),
    path('displacement_amplitude/', dashboard_views.displacement_amplitude_list),
    path('displacement_frequency/', dashboard_views.displacement_frequency_list),
    path('get_displacement_amplitude/', dashboard_views.get_displacement_amplitude),
    path('get_displacement_frequency/', dashboard_views.get_displacement_frequency),
    path('velocity_rms/', dashboard_views.velocity_rms_list),
    path('get_velocty_rms_range/', dashboard_views.get_velocity_rms_range_data),
    path('harmonics/', dashboard_views.harmonics_list),
    path('get_harmonics_data/', dashboard_views.get_harmonics_data),
    path('harmonics_filter_data/', dashboard_views.harmonics_filter_data),
    path('get_devices/', dashboard_views.get_devices),
    path('get_timestamp/', dashboard_views.get_timestamp),
    path('get_device_status/', dashboard_views.get_device_status),
    path('get_device_location/', dashboard_views.get_device_location),
    path('envelope_amplitude/', dashboard_views.envelope_amplitude_list),
    path('envelope_frequency/', dashboard_views.envelope_frequency_list),
    path('get_envelope_amplitude/', dashboard_views.get_envelope_amplitude),
    path('get_envelope_frequency/', dashboard_views.get_envelope_frequency),
    path('asset_health_score/', dashboard_views.asset_health_score_list),
    path('testApi/', dashboard_views.testApi),
    path('get_devices_list/', dashboard_views.getDeviceList),
    path('get_alarm_plot_data_time/', dashboard_views.getPlotDataTime),
    path('get_alarm_plot_data_freq/', dashboard_views.getPlotDataFreq),
    path('threshold/', dashboard_views.thresholdValues),
    path('get_threshold/', dashboard_views.GetThresholdData),
    path('get_temp/', dashboard_views.GetTempData),
    path('wired_sensor_data/', dashboard_views.SaveWiredSensorData),
    path('get_wired_sensor_data/', dashboard_views.GetWiredSensorData)
]