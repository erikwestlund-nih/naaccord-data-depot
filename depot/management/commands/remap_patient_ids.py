"""
Django management command to remap patient IDs in test data files.
Takes unrealistic sequential IDs and remaps them to realistic cohort patterns.
"""
import csv
import random
import sys
from pathlib import Path
from collections import Counter
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = 'Remap patient IDs in data files to match realistic cohort patterns'

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
            default=10,
            help='Average number of records per patient ID (default: 10)'
        )
        parser.add_argument(
            '--sample-size',
            type=int,
            help='Limit output to N rows (optional, for faster testing)'
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
        parser.add_argument(
            '--delimiter',
            type=str,
            help='CSV delimiter (auto-detect if not specified)'
        )
        parser.add_argument(
            '--preserve-order',
            action='store_true',
            help='Try to preserve relative ordering of patient records'
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

        # Process files
        self.stdout.write(f"Loading patient IDs from: {patient_file}")
        valid_ids = self.load_patient_ids(patient_file, options['patient_column'], options['delimiter'])

        if not valid_ids:
            raise CommandError("No patient IDs found in patient file")

        self.stdout.write(f"Loaded {len(valid_ids)} unique patient IDs")

        # Generate invalid IDs if requested
        invalid_ids = []
        if options['invalid_ratio'] > 0:
            # Ensure at least 1 invalid ID if ratio > 0
            num_invalid = max(1, int(len(valid_ids) * options['invalid_ratio']))
            invalid_ids = [f"{options['invalid_pattern']}{i:06d}" for i in range(num_invalid)]
            self.stdout.write(f"Generated {len(invalid_ids)} invalid IDs")

        # Create mapping
        self.stdout.write(f"Processing data file: {data_file}")
        stats = self.remap_file(
            data_file,
            output_file,
            valid_ids,
            invalid_ids,
            options
        )

        # Display statistics
        if options['show_stats']:
            self.display_stats(stats)

        self.stdout.write(self.style.SUCCESS(f"Successfully created: {output_file}"))

    def detect_delimiter(self, file_path):
        """Auto-detect CSV delimiter."""
        with open(file_path, 'r') as f:
            sample = f.read(1024)
            sniffer = csv.Sniffer()
            try:
                delimiter = sniffer.sniff(sample).delimiter
                return delimiter
            except:
                # Default to comma if detection fails
                return ','

    def load_patient_ids(self, patient_file, patient_column, delimiter=None):
        """Load unique patient IDs from patient file."""
        if delimiter is None:
            delimiter = self.detect_delimiter(patient_file)
            self.stdout.write(f"Detected delimiter: '{delimiter}'")

        patient_ids = set()

        with open(patient_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f, delimiter=delimiter)

            # Check if patient column exists
            if patient_column not in reader.fieldnames:
                # Try case-insensitive match
                for field in reader.fieldnames:
                    if field.lower() == patient_column.lower():
                        patient_column = field
                        break
                else:
                    raise CommandError(
                        f"Column '{patient_column}' not found. "
                        f"Available columns: {', '.join(reader.fieldnames)}"
                    )

            for row in reader:
                patient_id = row[patient_column]
                if patient_id and patient_id.strip():
                    patient_ids.add(patient_id.strip())

        return list(patient_ids)

    def remap_file(self, input_file, output_file, valid_ids, invalid_ids, options):
        """Remap patient IDs in data file."""
        delimiter = options.get('delimiter')
        if delimiter is None:
            delimiter = self.detect_delimiter(input_file)

        patient_column = options['patient_column']
        duplicate_factor = options['duplicate_factor']
        invalid_ratio = options['invalid_ratio']
        sample_size = options.get('sample_size')
        preserve_order = options.get('preserve_order', False)

        # Combine ID pools based on ratio
        all_ids = valid_ids.copy()
        if invalid_ids:
            all_ids.extend(invalid_ids)
            # Adjust selection probabilities
            # We want invalid_ratio of selections to be invalid
            weights = [1.0 - invalid_ratio] * len(valid_ids) + [invalid_ratio] * len(invalid_ids)
        else:
            weights = None

        # Statistics tracking
        stats = {
            'total_rows': 0,
            'remapped_rows': 0,
            'skipped_rows': 0,
            'id_distribution': Counter(),
            'valid_count': 0,
            'invalid_count': 0
        }

        # Create mapping cache for consistent remapping
        id_mapping = {}

        # For preserve_order mode, pre-assign IDs to ranges
        if preserve_order:
            # Count total unique IDs in input
            self.stdout.write("Scanning file to count unique IDs...")
            unique_input_ids = self.count_unique_ids(input_file, patient_column, delimiter)
            self.stdout.write(f"Found {len(unique_input_ids)} unique IDs to remap")

            # Assign each input ID to a patient ID with duplication
            for i, input_id in enumerate(sorted(unique_input_ids)):
                # Round-robin assignment with duplication factor
                patient_idx = (i // duplicate_factor) % len(valid_ids)
                id_mapping[input_id] = valid_ids[patient_idx]

        # Process file
        rows_processed = 0
        with open(input_file, 'r', encoding='utf-8-sig') as infile:
            reader = csv.DictReader(infile, delimiter=delimiter)

            # Check if patient column exists
            if patient_column not in reader.fieldnames:
                # Try case-insensitive match
                for field in reader.fieldnames:
                    if field.lower() == patient_column.lower():
                        patient_column = field
                        break
                else:
                    raise CommandError(
                        f"Column '{patient_column}' not found in data file. "
                        f"Available columns: {', '.join(reader.fieldnames)}"
                    )

            with open(output_file, 'w', newline='', encoding='utf-8') as outfile:
                writer = csv.DictWriter(outfile, fieldnames=reader.fieldnames, delimiter=delimiter)
                writer.writeheader()

                for row in reader:
                    stats['total_rows'] += 1

                    # Get original ID
                    original_id = row[patient_column]

                    if original_id and original_id.strip():
                        original_id = original_id.strip()

                        # Get or create mapping
                        if original_id not in id_mapping:
                            if weights:
                                # Weighted random selection
                                id_mapping[original_id] = random.choices(all_ids, weights=weights)[0]
                            else:
                                # Uniform random selection
                                id_mapping[original_id] = random.choice(all_ids)

                        new_id = id_mapping[original_id]
                        row[patient_column] = new_id
                        stats['remapped_rows'] += 1
                        stats['id_distribution'][new_id] += 1

                        if new_id in valid_ids:
                            stats['valid_count'] += 1
                        else:
                            stats['invalid_count'] += 1
                    else:
                        stats['skipped_rows'] += 1

                    writer.writerow(row)
                    rows_processed += 1

                    # Progress indicator
                    if rows_processed % 100000 == 0:
                        self.stdout.write(f"Processed {rows_processed:,} rows...")

                    # Sample size limit
                    if sample_size and rows_processed >= sample_size:
                        self.stdout.write(f"Reached sample size limit: {sample_size}")
                        break

        stats['unique_ids_used'] = len(id_mapping)
        return stats

    def count_unique_ids(self, input_file, patient_column, delimiter):
        """Count unique patient IDs in input file."""
        unique_ids = set()

        with open(input_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f, delimiter=delimiter)

            for row in reader:
                patient_id = row.get(patient_column, '').strip()
                if patient_id:
                    unique_ids.add(patient_id)

        return unique_ids

    def display_stats(self, stats):
        """Display processing statistics."""
        self.stdout.write("\n" + "="*60)
        self.stdout.write("PROCESSING STATISTICS")
        self.stdout.write("="*60)

        self.stdout.write(f"Total rows processed: {stats['total_rows']:,}")
        self.stdout.write(f"Rows remapped: {stats['remapped_rows']:,}")
        self.stdout.write(f"Rows skipped (empty ID): {stats['skipped_rows']:,}")
        self.stdout.write(f"Unique IDs in output: {stats['unique_ids_used']:,}")

        if stats['invalid_count'] > 0:
            valid_pct = (stats['valid_count'] / stats['remapped_rows']) * 100
            invalid_pct = (stats['invalid_count'] / stats['remapped_rows']) * 100
            self.stdout.write(f"\nValid IDs: {stats['valid_count']:,} ({valid_pct:.1f}%)")
            self.stdout.write(f"Invalid IDs: {stats['invalid_count']:,} ({invalid_pct:.1f}%)")

        # Show distribution of top 10 most common IDs
        self.stdout.write(f"\nTop 10 most frequent patient IDs:")
        for patient_id, count in stats['id_distribution'].most_common(10):
            self.stdout.write(f"  {patient_id}: {count:,} records")

        # Calculate distribution statistics
        counts = list(stats['id_distribution'].values())
        if counts:
            avg_records = sum(counts) / len(counts)
            min_records = min(counts)
            max_records = max(counts)

            self.stdout.write(f"\nDistribution summary:")
            self.stdout.write(f"  Average records per patient: {avg_records:.1f}")
            self.stdout.write(f"  Min records per patient: {min_records}")
            self.stdout.write(f"  Max records per patient: {max_records}")

        self.stdout.write("="*60 + "\n")