from django.core.management.base import BaseCommand
from django.utils import timezone
import logging

from app.cache import load_mount_data_mapping, \
                        load_sensor_orientation_mapping, \
                            load_threshold_data_mapping, \
                                load_threshold_counter_data_mapping

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Load and dump Redis data mappings - run once during startup'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-mount',
            action='store_true',
            help='Skip loading mount mapping data',
        )
        parser.add_argument(
            '--skip-orientation',
            action='store_true',
            help='Skip loading sensor orientation mapping',
        )
        parser.add_argument(
            '--skip-threshold',
            action='store_true',
            help='Skip loading threshold data mapping',
        )
        parser.add_argument(
            '--skip-counter',
            action='store_true',
            help='Skip loading threshold counter data mapping',
        )
    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS(f'Starting Redis data loading at {timezone.now()}')
        )

        try:
            # Load mount mapping
            if not options['skip_mount']:
                self.stdout.write('Loading mount mapping data...')
                mount_mapping = load_mount_data_mapping()
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Mount mapping loaded: {len(mount_mapping)} records')
                )

            # Load orientation mapping
            if not options['skip_orientation']:
                self.stdout.write('Loading sensor orientation mapping...')
                orientation_mapping = load_sensor_orientation_mapping()
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Orientation mapping loaded: {len(orientation_mapping)} records')
                )

            # Load threshold data
            if not options['skip_threshold']:
                self.stdout.write('Loading threshold data mapping...')
                thresh_data = load_threshold_data_mapping()
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Threshold data loaded: {len(thresh_data)} records')
                )

            # Load threshold counter data
            if not options['skip_counter']:
                self.stdout.write('Loading threshold counter data mapping...')
                thresh_counter_data = load_threshold_counter_data_mapping()
                self.stdout.write(
                    self.style.SUCCESS(f'✓ Threshold counter data loaded: {len(thresh_counter_data)} records')
                )

            self.stdout.write(
                self.style.SUCCESS(f'All Redis data loading completed successfully at {timezone.now()}')
            )

        except Exception as e:
            logger.error(f"Error in initialize_cache command: {str(e)}")
            self.stdout.write(
                self.style.ERROR(f'Error loading Redis data: {str(e)}')
            )
            raise e
