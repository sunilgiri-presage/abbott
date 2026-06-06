from django.core.management.base import BaseCommand
import json
import os
from datetime import datetime
import pytz
from app.models import RawDataMaster  # Replace 'your_app' with your actual app name


class Command(BaseCommand):
    help = 'Export raw_data for all three axes for specific timestamp and composite combinations'

    def add_arguments(self, parser):
        parser.add_argument(
            'data',
            nargs='+',
            type=str,
            help='Pairs of timestamp:composite (e.g., 1764424807:w_FC:B4:67:DA:96:44_6718a54336ad1e052e8ae1a3_84)'
        )

    def parse_timestamp(self, timestamp_str):
        """Parse timestamp from string or epoch format"""
        try:
            if timestamp_str.isdigit():
                timestamp = datetime.fromtimestamp(int(timestamp_str), tz=pytz.UTC)
                return timestamp
            else:
                timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                timestamp = pytz.UTC.localize(timestamp)
                return timestamp
        except Exception as e:
            raise ValueError(f"Invalid timestamp format: {timestamp_str}")

    def export_single_record(self, timestamp_str, composite, output_dir):
        """Export data for a single timestamp and composite combination"""
        try:
            timestamp = self.parse_timestamp(timestamp_str)
            
            axes = ['Vertical', 'Axial', 'Horizontal']
            result = {
                'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'fs': None,
                'composite': composite,
                'data': {}
            }
            
            for axis in axes:
                record = RawDataMaster.objects.filter(
                    timestamp=timestamp,
                    composite=composite,
                    axis=axis
                ).first()
                
                if record:
                    result['data'][axis] = record.raw_data
                    if result['fs'] is None:
                        result['fs'] = record.fs
            
            if not result['data']:
                self.stdout.write(self.style.WARNING(f'No data found for timestamp: {timestamp_str}, composite: {composite}'))
                return None
            
            filename = f'raw_data_{timestamp.strftime("%Y%m%d_%H%M%S")}_{composite}.json'
            filepath = os.path.join(output_dir, filename)
            
            if os.path.exists(filepath):
                self.stdout.write(self.style.WARNING(f'⚠ File already exists: {filename}'))
                return None
            
            with open(filepath, 'w') as f:
                json.dump(result, f, indent=4)
            
            self.stdout.write(self.style.SUCCESS(f'✓ Exported: {filename}'))
            self.stdout.write(self.style.SUCCESS(f'  Axes: {", ".join(result["data"].keys())} | FS: {result["fs"]}'))
            
            return filename
            
        except ValueError as e:
            self.stdout.write(self.style.ERROR(str(e)))
            return None
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error processing {timestamp_str}:{composite}: {str(e)}'))
            return None

    def handle(self, *args, **options):
        data_pairs = options['data']
        
        output_dir = 'raw_data'
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            self.stdout.write(self.style.NOTICE(f'Created directory: {output_dir}\n'))
        
        self.stdout.write(self.style.NOTICE(f'Processing {len(data_pairs)} record(s)...\n'))
        
        success_count = 0
        for pair in data_pairs:
            try:
                timestamp_str, composite = pair.split(':', 1)
                result = self.export_single_record(timestamp_str, composite, output_dir)
                if result:
                    success_count += 1
                self.stdout.write('')
            except ValueError:
                self.stdout.write(self.style.ERROR(f'Invalid format: {pair}. Use timestamp:composite'))
                self.stdout.write('')
        
        self.stdout.write(self.style.SUCCESS(f'=' * 50))
        self.stdout.write(self.style.SUCCESS(f'Successfully exported {success_count}/{len(data_pairs)} files'))
        self.stdout.write(self.style.SUCCESS(f'All files saved in: {output_dir}/'))
        self.stdout.write(self.style.SUCCESS(f'=' * 50))