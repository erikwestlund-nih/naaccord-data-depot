import subprocess
import os
from pathlib import Path
from django.conf import settings
from depot.models import Notebook, PrecheckRun, PHIFileTracking
from depot.storage.manager import StorageManager
import tempfile
import shutil
from depot.data.notebook_templates import notebook_templates
import logging
import time

logger = logging.getLogger(__name__)

class NotebookService:
    """Service for handling notebook compilation and management."""

    def __init__(self, notebook: Notebook):
        self.notebook = notebook
        self.storage = StorageManager.get_storage('reports')
        self.temp_dir = None
        self.quarto_config = settings.QUARTO_CONFIG

    def compile(self):
        """Compile the notebook to HTML."""
        try:
            logger.info(f"Starting compilation for notebook {self.notebook.id}")
            self.notebook.mark_compiling()
            
            logger.info("Setting up temp directory")
            self._setup_temp_dir()
            
            logger.info("Copying template")
            self._copy_template()
            
            logger.info("Running Quarto")
            self._run_quarto()
            
            # If _run_quarto returned early, mark as failed and return
            if not hasattr(self, '_quarto_completed'):
                error_msg = "DuckDB file path not found in audit result"
                logger.error(error_msg)
                self.notebook.mark_failed(error_msg)
                return False
            
            logger.info("Storing compiled notebook")
            self._store_compiled()
            
            logger.info(f"Successfully compiled notebook {self.notebook.id}")
            return True
        except FileNotFoundError as e:
            error_msg = f"File not found during notebook compilation: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.notebook.mark_failed(error_msg)
            return False
        except subprocess.CalledProcessError as e:
            error_msg = f"Quarto compilation failed: {e.stderr if e.stderr else str(e)}"
            logger.error(error_msg, exc_info=True)
            self.notebook.mark_failed(error_msg)
            return False
        except Exception as e:
            error_msg = f"Unexpected error during notebook compilation: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.notebook.mark_failed(error_msg)
            return False
        finally:
            logger.info("Cleaning up temporary files")
            self._cleanup()

    def _setup_temp_dir(self):
        """Set up temporary directory for compilation."""
        self.temp_dir = Path(tempfile.mkdtemp(prefix='notebook_compile_'))
        logger.info(f"Created temp directory: {self.temp_dir}")

        # Create .here file so here::here() recognizes this as project root
        here_file = self.temp_dir / '.here'
        here_file.touch()
        logger.info(f"Created .here marker file: {here_file}")

    def _copy_template(self):
        """Copy the notebook template to the temp directory."""
        template_path = self.notebook.get_template_path()
        logger.info(f"Template path: {template_path}")

        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        # Create depot/notebooks directory structure for here::here() compatibility
        depot_dir = self.temp_dir / 'depot'
        depot_notebooks_dir = depot_dir / 'notebooks'
        depot_notebooks_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created depot/notebooks directory: {depot_notebooks_dir}")

        # Copy scaffold_r.R to depot/ (for here::here("depot", "scaffold_r.R"))
        # scaffold_r.R is at depot/scaffold_r.R, and settings.BASE_DIR is /app/
        scaffold_r_source = Path(settings.BASE_DIR) / 'depot' / 'scaffold_r.R'
        if scaffold_r_source.exists():
            scaffold_r_target = depot_dir / 'scaffold_r.R'
            logger.info(f"Copying scaffold_r.R to: {scaffold_r_target}")
            shutil.copy2(scaffold_r_source, scaffold_r_target)
        else:
            logger.warning(f"scaffold_r.R not found at: {scaffold_r_source}")

        # Copy depot/R directory (for load_depot_r() function)
        # depot/R is at depot/R, and settings.BASE_DIR is /app/
        r_source_dir = Path(settings.BASE_DIR) / 'depot' / 'R'
        if r_source_dir.exists():
            r_target_dir = depot_dir / 'R'
            logger.info(f"Copying depot/R directory to: {r_target_dir}")
            shutil.copytree(r_source_dir, r_target_dir, dirs_exist_ok=True)
        else:
            logger.warning(f"depot/R directory not found at: {r_source_dir}")

        # Copy depot/data/definitions directory (for data definitions)
        definitions_source_dir = Path(settings.BASE_DIR) / 'depot' / 'data' / 'definitions'
        if definitions_source_dir.exists():
            definitions_target_dir = depot_dir / 'data' / 'definitions'
            logger.info(f"Copying depot/data/definitions directory to: {definitions_target_dir}")
            shutil.copytree(definitions_source_dir, definitions_target_dir, dirs_exist_ok=True)
        else:
            logger.warning(f"depot/data/definitions directory not found at: {definitions_source_dir}")

        # Create partials directory
        partials_dir = depot_notebooks_dir / 'partials'
        partials_dir.mkdir(exist_ok=True)
        logger.info(f"Created partials directory: {partials_dir}")

        # Copy the main template to depot/notebooks/
        target_path = depot_notebooks_dir / 'notebook.qmd'
        logger.info(f"Copying template to: {target_path}")
        shutil.copy2(template_path, target_path)

        # Copy entire partials directory
        partials_source_dir = template_path.parent / 'partials'
        if partials_source_dir.exists():
            logger.info(f"Copying partials directory from: {partials_source_dir}")
            shutil.copytree(partials_source_dir, partials_dir, dirs_exist_ok=True)
        else:
            logger.warning(f"Partials directory not found: {partials_source_dir}")

        # Copy CSS files to depot/notebooks/
        for css_file in ['styles.css', 'cosmo-bootstrap.min.css']:
            css_source = template_path.parent / css_file
            if css_source.exists():
                css_target = depot_notebooks_dir / css_file
                logger.info(f"Copying CSS file: {css_file}")
                shutil.copy2(css_source, css_target)
            else:
                logger.warning(f"CSS file not found: {css_source}")

        # Copy setup.R to depot/notebooks/ (same directory as notebook.qmd)
        setup_r_source = template_path.parent.parent / 'setup.R'
        if setup_r_source.exists():
            setup_r_target = depot_notebooks_dir / 'setup.R'
            logger.info(f"Copying setup.R to: {setup_r_target}")
            shutil.copy2(setup_r_source, setup_r_target)
        else:
            logger.error(f"setup.R not found at: {setup_r_source}")

        # Copy notebooks/functions directory (for init_audit_data and other functions)
        functions_source_dir = template_path.parent.parent / 'functions'
        if functions_source_dir.exists():
            functions_target_dir = depot_notebooks_dir / 'functions'
            logger.info(f"Copying notebooks/functions directory to: {functions_target_dir}")
            shutil.copytree(functions_source_dir, functions_target_dir, dirs_exist_ok=True)
        else:
            logger.warning(f"notebooks/functions directory not found at: {functions_source_dir}")

    def _run_quarto(self):
        """Run Quarto to compile the notebook."""
        # Get notebook and data paths
        notebook_path = self.notebook.get_template_path()
        if self.notebook.content_object and isinstance(self.notebook.content_object, PrecheckRun):
            precheck_run = self.notebook.content_object
            logger.info(f"PrecheckRun status: {precheck_run.status}")

            # Get definition file name from the data file type
            definition_file = f"{precheck_run.data_file_type.name}_definition.json"
            # Get DuckDB path from precheck_run result
            if precheck_run.result and isinstance(precheck_run.result, dict):
                # The temp_file is nested in the result structure
                if 'result' in precheck_run.result and isinstance(precheck_run.result['result'], dict):
                    if 'temp_file' in precheck_run.result['result']:
                        data_file_path = Path(precheck_run.result['result']['temp_file'])
                        logger.info(f"Using DuckDB path: {data_file_path}")
                    else:
                        error_msg = "temp_file not found in precheck_run.result['result']"
                        logger.error(error_msg)
                        raise ValueError(error_msg)
                else:
                    error_msg = "precheck_run.result['result'] not found or not a dict"
                    logger.error(error_msg)
                    raise ValueError(error_msg)
            else:
                error_msg = "precheck_run.result not found or not a dict"
                logger.error(error_msg)
                raise ValueError(error_msg)
        else:
            error_msg = "Notebook content_object is not an PrecheckRun instance"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Native execution - no container
        logger.info("Using native Quarto execution")

        # Set up environment variables
        env = os.environ.copy()
        env['DATA_FILE_TYPE'] = self.notebook.data_file_type.name
        env['DATA_FILE_PATH'] = str(data_file_path)
        env['DEFINITION_FILE'] = definition_file

        # Run Quarto on the copied template in depot/notebooks/
        # Use the temp copy so we have write permissions
        temp_notebook_path = self.temp_dir / 'depot' / 'notebooks' / 'notebook.qmd'
        cmd = [
            'quarto', 'render', str(temp_notebook_path),
            '-P', f'data_file_type={self.notebook.data_file_type.name}',
            '-P', f'data_file_path={str(data_file_path)}',
            '-P', f'definition_file={definition_file}'
        ]

        # Use the temp directory root as working directory (for here::here() to work)
        working_dir = self.temp_dir

        logger.info(f"Running Quarto on original notebook: {notebook_path}")
        logger.info(f"Output directory: {self.temp_dir}")
        logger.info(f"Working directory: {working_dir}")
        result = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=str(working_dir))

        # Always log stdout/stderr for debugging
        if result.stdout:
            logger.info(f"Quarto stdout:\n{result.stdout}")
        if result.stderr:
            logger.info(f"Quarto stderr:\n{result.stderr}")

        if result.returncode != 0:
            # Check for R debug log even on failure
            import tempfile as tmp
            debug_log = Path(tmp.gettempdir()) / 'setup_production_debug.log'
            if debug_log.exists():
                logger.error("=== R Setup Debug Log (from failed run) ===")
                with open(debug_log, 'r') as f:
                    for line in f:
                        logger.error(f"R: {line.rstrip()}")
                logger.error("=== End R Setup Debug Log ===")
            else:
                logger.warning(f"R debug log not found at: {debug_log}")

            error_msg = f"Quarto compilation failed. stderr: {result.stderr}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info("Native Quarto execution completed successfully")

        # Check for R debug log and output it
        import tempfile as tmp
        debug_log = Path(tmp.gettempdir()) / 'setup_production_debug.log'
        if debug_log.exists():
            logger.info("=== R Setup Debug Log ===")
            with open(debug_log, 'r') as f:
                for line in f:
                    logger.info(f"R: {line.rstrip()}")
            logger.info("=== End R Setup Debug Log ===")
        else:
            logger.warning(f"R debug log not found at: {debug_log}")

        # Quarto creates notebook.html in depot/notebooks/ (same dir as notebook.qmd)
        output_html = self.temp_dir / 'depot' / 'notebooks' / 'notebook.html'
        if output_html.exists():
            # Move to temp root for consistency with _store_compiled expectations
            final_html = self.temp_dir / 'notebook.html'
            shutil.move(str(output_html), str(final_html))
            logger.info(f"Moved HTML from {output_html} to {final_html}")
        else:
            logger.error(f"HTML file not found at {output_html}")
            logger.info(f"Files in depot/notebooks: {list((self.temp_dir / 'depot' / 'notebooks').iterdir())}")

        # Mark that Quarto completed successfully
        self._quarto_completed = True


    def _store_compiled(self):
        """Store the compiled notebook in the storage backend."""
        # Try both possible output filenames
        possible_paths = [
            self.temp_dir / 'notebook.html',
            self.temp_dir / 'generic_audit.html'
        ]
        
        # Try to find the compiled file with retries
        max_retries = 5
        retry_delay = 2  # seconds
        compiled_path = None
        
        for i in range(max_retries):
            for path in possible_paths:
                if path.exists():
                    compiled_path = path
                    break
            if compiled_path:
                break
            logger.info(f"Waiting for compiled notebook (attempt {i+1}/{max_retries})")
            time.sleep(retry_delay)
        
        if not compiled_path:
            raise FileNotFoundError(f"Compiled notebook not found in {self.temp_dir} after {max_retries} attempts")

        # Generate storage path under notebooks namespace
        if self.notebook.content_object and isinstance(self.notebook.content_object, PrecheckRun):
            precheck_run = self.notebook.content_object
            # PrecheckRun may not have a cohort (it's optional for prechecks)
            if precheck_run.cohort:
                storage_path = f"notebooks/{precheck_run.cohort.id}/{self.notebook.id}/report.html"
            else:
                storage_path = f"notebooks/precheck_run/{self.notebook.id}/report.html"
        else:
            storage_path = f"notebooks/{self.notebook.id}/report.html"
        
        logger.info(f"Storing compiled notebook at: {storage_path}")
        logger.info(f"Source file size: {compiled_path.stat().st_size} bytes")
        
        # Read the file content and pass it directly
        try:
            with open(compiled_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            # Save to storage
            url = self.storage.save(
                storage_path, 
                html_content,  # Pass content directly, not file handle
                content_type='text/html'
            )
            
            # Debug the stored file
            debug_info = self.storage.debug_file(storage_path)
            if debug_info:
                logger.info("Stored file debug info:")
                logger.info(f"  Content-Type: {debug_info['content_type']}")
                logger.info(f"  Content-Length: {debug_info['content_length']}")
                logger.info(f"  Metadata: {debug_info['metadata']}")
            
            logger.info(f"Successfully stored compiled notebook at: {url}")

            # Create PHI tracking record for audit trail
            try:
                # Extract user and cohort from notebook's content_object
                user = None
                cohort = None
                if self.notebook.content_object and isinstance(self.notebook.content_object, PrecheckRun):
                    precheck_run = self.notebook.content_object
                    user = precheck_run.uploaded_by
                    cohort = precheck_run.cohort

                file_size = len(html_content.encode('utf-8'))

                # Get absolute path for PHI tracking
                absolute_path = self.storage.get_absolute_path(storage_path)

                PHIFileTracking.objects.create(
                    cohort=cohort,
                    user=user,
                    action='nas_report_created',
                    file_path=absolute_path,  # Use absolute path
                    file_type='report_html',
                    file_size=file_size,
                    content_object=self.notebook,
                    cleanup_required=False,  # Reports are permanent
                    server_role=os.environ.get('SERVER_ROLE', 'testing'),
                    metadata={
                        'notebook_id': self.notebook.id,
                        'data_file_type': self.notebook.data_file_type.name,
                        'relative_path': storage_path
                    }
                )
                logger.info(f"PHI tracking created for report: {absolute_path}")
            except Exception as e:
                # Log error but don't fail report generation
                logger.error(f"Failed to create PHI tracking record for report: {e}", exc_info=True)

            # Update notebook record
            self.notebook.mark_completed(storage_path)
            return url
            
        except Exception as e:
            logger.error(f"Failed to store compiled notebook: {e}")
            raise

    def _cleanup(self):
        """Clean up temporary files."""
        if self.temp_dir and self.temp_dir.exists():
            logger.info(f"Removing temp directory: {self.temp_dir}")
            shutil.rmtree(self.temp_dir)

    def _get_template_path(self, data_file_type_name: str) -> str:
        """Get the path to the template for a data file type."""
        template_name = notebook_templates.get_template(data_file_type_name)
        return str(self.templates_dir / template_name) 