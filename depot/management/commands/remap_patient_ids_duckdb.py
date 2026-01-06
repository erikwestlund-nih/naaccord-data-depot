"""
Django management command to remap patient IDs using DuckDB for speed.
Orders of magnitude faster than CSV streaming for large files.
"""
import random
import duckdb
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Remap patient IDs using DuckDB for high-performance processing'

    def add_arguments(self, parser):
        # Required arguments
        parser.add_argument(
            '--patient-file',
            type=str,
            required=True,
            help='Path to patient file containing valid patient IDs'
        )
        parser.add_argument(
            '--data-file',
            type=str,
            required=True,
            help='Path to data file with patient IDs to remap'
        )

        # Optional arguments
        parser.add_argument(
            '--output',
            type=str,
            help='Output file path (default: <input>_remapped.csv)'
        )
        parser.add_argument(
            '--patient-column',
            type=str,
            default='cohortPatientId',
            help='Name of patient ID column (default: cohortPatientId)'
        )
        parser.add_argument(
            '--invalid-ratio',
            type=float,
            default=0.0,
            help='Ratio of invalid IDs to inject (0.0-1.0, default: 0.0)'
        )
        parser.add_argument(
            '--duplicate-factor',
            type=int,
            default=20,
            help='Average number of records per patient ID (default: 20)'
        )
        parser.add_argument(
            '--invalid-pattern',
            type=str,
            default='INVALID_',
            help='Prefix for invalid IDs (default: INVALID_)'
        )
        parser.add_argument(
            '--seed',
            type=int,
            help='Random seed for reproducible results'
        )
        parser.add_argument(
            '--show-stats',
            action='store_true',
            help='Display distribution statistics after processing'
        )

    def handle(self, *args, **options):
        # Set random seed if provided
        if options['seed']:
            random.seed(options['seed'])
            self.stdout.write(f"Using random seed: {options['seed']}")

        # Validate files exist
        patient_file = Path(options['patient_file'])
        data_file = Path(options['data_file'])

        if not patient_file.exists():
            raise CommandError(f"Patient file not found: {patient_file}")
        if not data_file.exists():
            raise CommandError(f"Data file not found: {data_file}")

        # Determine output file
        if options['output']:
            output_file = Path(options['output'])
        else:
            output_file = data_file.parent / f"{data_file.stem}_remapped{data_file.suffix}"

        # Process with DuckDB
        self.stdout.write(f"Processing with DuckDB...")

        # Connect to DuckDB (in-memory for speed)
        conn = duckdb.connect(':memory:')

        try:
            # Load patient file
            self.stdout.write(f"Loading patient IDs from: {patient_file}")
            patient_column = options['patient_column']

            # Read patient file and get unique IDs
            conn.execute(f"""
                CREATE TABLE patients AS
                SELECT DISTINCT "{patient_column}" as patient_id
                FROM read_csv_auto('{patient_file}')
                WHERE "{patient_column}" IS NOT NULL
            """)

            patient_count = conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
            self.stdout.write(f"Loaded {patient_count} unique patient IDs")

            # Get patient IDs into Python for mapping generation
            patient_ids = [row[0] for row in conn.execute("SELECT patient_id FROM patients").fetchall()]

            # Generate invalid IDs if requested
            invalid_ids = []
            if options['invalid_ratio'] > 0:
                num_invalid = max(1, int(len(patient_ids) * options['invalid_ratio']))
                invalid_ids = [f"{options['invalid_pattern']}{i:06d}" for i in range(num_invalid)]
                self.stdout.write(f"Generated {len(invalid_ids)} invalid IDs")

            # Create mapping table
            self.stdout.write(f"Creating ID mapping table...")

            # Get unique IDs from data file
            conn.execute(f"""
                CREATE TABLE original_ids AS
                SELECT DISTINCT "{patient_column}" as old_id
                FROM read_csv_auto('{data_file}')
                WHERE "{patient_column}" IS NOT NULL
            """)

            original_count = conn.execute("SELECT COUNT(*) FROM original_ids").fetchone()[0]
            self.stdout.write(f"Found {original_count} unique IDs in data file")

            # Create mapping in Python
            original_ids = [row[0] for row in conn.execute("SELECT old_id FROM original_ids").fetchall()]

            # Combine valid and invalid IDs
            all_new_ids = patient_ids + invalid_ids
            weights = None
            if invalid_ids:
                # Weight selection for invalid ratio
                weights = [1.0 - options['invalid_ratio']] * len(patient_ids) + \
                         [options['invalid_ratio']] * len(invalid_ids)

            # Generate mappings
            id_mapping = {}
            for old_id in original_ids:
                if weights:
                    id_mapping[str(old_id)] = random.choices(all_new_ids, weights=weights)[0]
                else:
                    id_mapping[str(old_id)] = random.choice(patient_ids)

            # Create mapping table in DuckDB
            mapping_data = [(old, new) for old, new in id_mapping.items()]
            conn.execute("""
                CREATE TABLE id_mapping (
                    old_id VARCHAR,
                    new_id VARCHAR
                )
            """)
            conn.executemany("INSERT INTO id_mapping VALUES (?, ?)", mapping_data)

            # Process the file using JOIN
            self.stdout.write(f"Remapping IDs in data file...")

            # Read original file, join with mapping, write output
            # This is the fast part - DuckDB handles the join efficiently
            conn.execute(f"""
                COPY (
                    SELECT
                        data.* EXCLUDE("{patient_column}"),
                        COALESCE(mapping.new_id, CAST(data."{patient_column}" AS VARCHAR)) as "{patient_column}"
                    FROM read_csv_auto('{data_file}') data
                    LEFT JOIN id_mapping mapping
                    ON CAST(data."{patient_column}" AS VARCHAR) = mapping.old_id
                ) TO '{output_file}' (HEADER, DELIMITER ',')
            """)

            self.stdout.write(self.style.SUCCESS(f"Successfully created: {output_file}"))

            # Show statistics if requested
            if options['show_stats']:
                self.display_stats_duckdb(conn, output_file, patient_column, patient_ids, invalid_ids)

        finally:
            conn.close()

    def display_stats_duckdb(self, conn, output_file, patient_column, valid_ids, invalid_ids):
        """Display processing statistics using DuckDB."""

        # Get statistics from output file
        conn.execute(f"""
            CREATE TABLE output_data AS
            SELECT * FROM read_csv_auto('{output_file}')
        """)

        total_rows = conn.execute("SELECT COUNT(*) FROM output_data").fetchone()[0]
        unique_ids = conn.execute(f"""
            SELECT COUNT(DISTINCT "{patient_column}")
            FROM output_data
        """).fetchone()[0]

        self.stdout.write("\n" + "="*60)
        self.stdout.write("PROCESSING STATISTICS")
        self.stdout.write("="*60)
        self.stdout.write(f"Total rows processed: {total_rows:,}")
        self.stdout.write(f"Unique IDs in output: {unique_ids:,}")

        if invalid_ids:
            # Count valid vs invalid
            invalid_pattern = invalid_ids[0][:8] if invalid_ids else 'INVALID_'
            invalid_count = conn.execute(f"""
                SELECT COUNT(*)
                FROM output_data
                WHERE "{patient_column}" LIKE '{invalid_pattern}%'
            """).fetchone()[0]

            valid_count = total_rows - invalid_count
            valid_pct = (valid_count / total_rows) * 100
            invalid_pct = (invalid_count / total_rows) * 100

            self.stdout.write(f"\nValid IDs: {valid_count:,} ({valid_pct:.1f}%)")
            self.stdout.write(f"Invalid IDs: {invalid_count:,} ({invalid_pct:.1f}%)")

        # Show top 10 most common IDs
        self.stdout.write(f"\nTop 10 most frequent patient IDs:")
        top_ids = conn.execute(f"""
            SELECT "{patient_column}", COUNT(*) as cnt
            FROM output_data
            GROUP BY "{patient_column}"
            ORDER BY cnt DESC
            LIMIT 10
        """).fetchall()

        for patient_id, count in top_ids:
            self.stdout.write(f"  {patient_id}: {count:,} records")

        # Calculate distribution statistics
        dist_stats = conn.execute(f"""
            WITH id_counts AS (
                SELECT "{patient_column}", COUNT(*) as cnt
                FROM output_data
                GROUP BY "{patient_column}"
            )
            SELECT
                AVG(cnt) as avg_records,
                MIN(cnt) as min_records,
                MAX(cnt) as max_records
            FROM id_counts
        """).fetchone()

        self.stdout.write(f"\nDistribution summary:")
        self.stdout.write(f"  Average records per patient: {dist_stats[0]:.1f}")
        self.stdout.write(f"  Min records per patient: {dist_stats[1]}")
        self.stdout.write(f"  Max records per patient: {dist_stats[2]}")
        self.stdout.write("="*60 + "\n")