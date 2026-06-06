from django.apps import AppConfig
import ssl
import smtplib



class AppConfig(AppConfig):
    name = 'app'

    def ready(self):
        ssl._create_default_https_context = ssl._create_unverified_context
