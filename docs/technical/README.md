# NA-ACCORD Data Depot Technical Documentation

Technical documentation for the NA-ACCORD Data Depot system architecture, data flow, and implementation details.

## Table of Contents

1. [System Architecture](./architecture.md) - Overall system design and components
2. [File Storage System](./file-storage.md) - How files are stored and retrieved
3. [Upload Processing](./upload-processing.md) - File upload workflow and processing
4. [Validation Pipeline](./validation-pipeline.md) - Data validation using R/NAATools
5. [Data Models](./data-models.md) - Database schema and relationships
6. [API Endpoints](./api-endpoints.md) - REST API documentation
7. [Background Jobs](./background-jobs.md) - Celery task processing

## Key Components

### Core Technologies
- **Backend**: Django 5.x
- **Task Queue**: Celery with Redis
- **Data Processing**: R with NAATools package
- **Database**: MariaDB for metadata, DuckDB for data processing
- **Storage**: NAS network storage (driver architecture supports future S3-compatible migration)
- **Report Generation**: Quarto notebooks

## Development Setup

See the main README for development environment setup instructions.

## Architecture Overview

```
User → Django Web → Celery Tasks → R/NAATools → Storage
         ↓             ↓                ↓          ↓
      MariaDB       Redis           DuckDB       NAS
```

## Key Concepts

- **Submissions**: Container for all data files for a cohort/year
- **DataTables**: Individual data types within a submission
- **TemporaryFiles**: Uploaded files awaiting processing
- **Audits**: Validation run records with reports
- **Notebooks**: Quarto templates for report generation