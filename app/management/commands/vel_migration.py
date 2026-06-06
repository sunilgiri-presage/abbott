import pandas as pd
from django.db import transaction
from django.core.management.base import BaseCommand
from django.db.models import Q
from app.models import VelocityStatTimeMaster, VelocityStatTimeOptimized, MigrationProgressVel

BATCH_SIZE = 200000  # Number of rows per batch

def get_last_processed_id():
    """Retrieve the last processed ID from a tracking table or return 0 if not found."""
    progress = MigrationProgressVel.objects.first()
    return progress.last_processed_id if progress else 0

def update_last_processed_id(last_id):
    """Update the last processed ID to resume migration from the correct point."""
    MigrationProgressVel.objects.update_or_create(id=1, defaults={"last_processed_id": last_id})

def migrate_velocity_data():
    print("🚀 Starting batch-wise migration...")

    last_processed_id = get_last_processed_id()
    print(f"🔄 Resuming from ID: {last_processed_id}")

    while True:
        queryset = VelocityStatTimeMaster.objects.filter(
            id__gt=last_processed_id
        ).order_by("id")[:BATCH_SIZE]  # Fetch a batch efficiently

        if not queryset.exists():
            print("✅ No more records left to process. Migration completed!")
            break  # Exit if no data left

        # Convert queryset to Pandas DataFrame
        df = pd.DataFrame(list(queryset.values(
            "id", "timestamp", "composite", "axis", "rms", "peak", "peak_to_peak", "kurtosis",
            "flag", "rms_only", "asset_id", "mount_id"
        )))

        if df.empty:
            print("✅ No more records left to process. Migration completed!")
            break  # Exit if no data left

        # **STEP 1: Pivot table to merge Axial, Vertical, Horizontal values into one row per (timestamp, composite)**
        df_pivot = df.pivot_table(
            index=["timestamp", "composite"],
            columns="axis",
            values=["rms", "peak", "peak_to_peak", "kurtosis"],
            aggfunc="first"
        )

        # Flatten multi-level column names
        df_pivot.columns = ["_".join(col).strip() for col in df_pivot.columns]
        df_pivot.reset_index(inplace=True)

        # **STEP 2: Rename columns to match Django model fields**
        column_mapping = {
            "rms_Axial": "rms_Axial", "rms_Vertical": "rms_Vertical", "rms_Horizontal": "rms_Horizontal",
            "peak_Axial": "peak_Axial", "peak_Vertical": "peak_Vertical", "peak_Horizontal": "peak_Horizontal",
            "peak_to_peak_Axial": "peak_to_peak_Axial", "peak_to_peak_Vertical": "peak_to_peak_Vertical", "peak_to_peak_Horizontal": "peak_to_peak_Horizontal",
            "kurtosis_Axial": "kurtosis_Axial", "kurtosis_Vertical": "kurtosis_Vertical", "kurtosis_Horizontal": "kurtosis_Horizontal"
        }
        df_pivot.rename(columns=column_mapping, inplace=True)

        # **STEP 3: Merge flag and metadata columns**
        df_meta = df.groupby(["timestamp", "composite"])[["flag", "rms_only", "asset_id", "mount_id"]].first().reset_index()
        df_final = df_pivot.merge(df_meta, on=["timestamp", "composite"], how="left")

        # **STEP 4: Remove Duplicate Rows (Keeping the Most Recent Entry)**
        df_final = df_final.drop_duplicates(subset=["timestamp", "mount_id", "composite"], keep="last")

        # **STEP 5: Convert DataFrame to list of Django model instances**
        batch_data = [
            VelocityStatTimeOptimized(
                timestamp=row["timestamp"],
                composite=row["composite"],
                mount_id=row["mount_id"],
                rms_Axial=row.get("rms_Axial"), rms_Vertical=row.get("rms_Vertical"), rms_Horizontal=row.get("rms_Horizontal"),
                peak_Axial=row.get("peak_Axial"), peak_Vertical=row.get("peak_Vertical"), peak_Horizontal=row.get("peak_Horizontal"),
                peak_to_peak_Axial=row.get("peak_to_peak_Axial"), peak_to_peak_Vertical=row.get("peak_to_peak_Vertical"), peak_to_peak_Horizontal=row.get("peak_to_peak_Horizontal"),
                kurtosis_Axial=row.get("kurtosis_Axial"), kurtosis_Vertical=row.get("kurtosis_Vertical"), kurtosis_Horizontal=row.get("kurtosis_Horizontal"),
                flag=row.get("flag", False),
                rms_only=row.get("rms_only", False),
                asset_id=row.get("asset_id"),
            )
            for _, row in df_final.iterrows()
        ]

        # **STEP 6: Delete Existing Conflicting Rows Using `Q` Operator**
        with transaction.atomic():
            VelocityStatTimeOptimized.objects.bulk_create(batch_data, batch_size=BATCH_SIZE)

        # **STEP 8: Update last processed ID**
        last_processed_id = df["id"].max()
        update_last_processed_id(last_processed_id)

        print(f"✅ Processed up to ID: {last_processed_id}")

    print("🎉 Migration completed successfully!")


class Command(BaseCommand):
    help = "Migrate Velocity Data using Pandas"

    def handle(self, *args, **kwargs):
        migrate_velocity_data()
