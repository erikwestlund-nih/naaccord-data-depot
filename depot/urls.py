"""
URL configuration for depot project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings

# Custom error handlers
handler403 = 'depot.views.errors.handler403'
handler404 = 'depot.views.errors.handler404'
handler500 = 'depot.views.errors.handler500'

from depot.components.pages.submissions.upload import SubmissionsUploadPage
from depot.decorators import anonymous_required
from depot.views.account import account_page
from depot.views.upload_precheck import precheck_run_page, precheck_run_status, precheck_run_upload
from depot.views.precheck_validation import precheck_validation_page, precheck_validation_upload, precheck_validation_status, precheck_validation_status_json, precheck_validation_status_api, precheck_validation_status_page, cohort_submissions_api
from depot.views.notebooks import notebook_view, notebook_download
from depot.views.auth.sign_in import sign_in_page
from depot.views.cohorts import cohorts_page
from depot.views.cohort_detail import cohort_detail
from depot.views.dashboard import dashboard_page
from depot.views.auth.sign_out import signout_view
from depot.views.auth.saml_login import saml_login_force_auth
from depot.auth.mock_idp import (
    MockSAMLLogin, MockIdPLogin, MockSAMLACS, 
    MockSAMLMetadata, MockSAMLLogout
)
from depot.views.index import index_page
from depot.views.submissions.index import submissions_page
from depot.views.submissions.upload import submissions_upload_page
from depot.views.submissions.protocolyears import protocol_years_page
from depot.views.submissions.create import submission_create_page
from depot.views.submissions.cohort_submissions import cohort_submissions_page
from depot.views.submissions.detail import submission_detail_page
from depot.views.submissions.table_manage import (
    submission_table_manage,
    download_patient_validation_csv,
    download_file_patient_validation_csv,
    revalidate_submission_file,
    revalidate_submission_variable,
    submission_validation_status,
    submission_validation_status_json,
    mark_file_failed,
    retry_file_processing,
)
from depot.views.upload import upload_temp_file
from depot.views.health import health_check
from depot.views.attachments import upload_attachment, upload_attachment_secure, upload_submission_attachment_secure, download_attachment, remove_attachment
from depot.views.api.review import (
    toggle_table_review,
    save_table_comments,
    save_file_comments,
    save_file_name,
    track_report_view,
    get_table_review_status,
    save_attachment_name,
    save_attachment_comments,
    delete_attachment,
    save_submission_final_comments
)
from depot.views.internal_storage import (
    storage_upload,
    storage_upload_chunked,
    storage_download,
    storage_delete,
    storage_delete_prefix,
    storage_list,
    storage_exists,
    storage_metadata,
    cleanup_scratch,
    storage_health,
)

urlpatterns = [
    # Public health check endpoint (no authentication required)
    path("health/", health_check, name="health_check"),

    path("", index_page, name="index"),
    path("upload-precheck", precheck_run_page, name="upload_precheck"),
    path("upload-precheck/upload", precheck_run_upload, name="upload_precheck_upload"),
    path("upload-precheck/reports/<int:precheck_run_id>", precheck_run_status, name="upload_precheck_status"),
    path("precheck-validation", precheck_validation_page, name="precheck_validation_page"),
    path("precheck-validation/upload", precheck_validation_upload, name="precheck_validation_upload"),
    path("precheck-validation/<int:validation_run_id>", precheck_validation_status, name="precheck_validation_status"),
    path("precheck-validation/<int:validation_run_id>/json", precheck_validation_status_json, name="precheck_validation_status_json"),
    # New diagnostic precheck validation endpoints
    path("precheck-validation/status/<int:validation_id>", precheck_validation_status_page, name="precheck_validation_status_page"),
    path("precheck-validation/api/<int:validation_id>/status", precheck_validation_status_api, name="precheck_validation_status_api"),
    path("api/cohorts/<int:cohort_id>/submissions/", cohort_submissions_api, name="cohort_submissions_api"),
    path("notebooks/<int:notebook_id>/view", notebook_view, name="notebook_view"),
    path("notebooks/<int:notebook_id>/download", notebook_download, name="notebook_download"),
    path("submissions", submissions_page, name="submissions"),
    path("protocol-years", protocol_years_page, name="protocol_years"),
    path("submissions/create", submission_create_page, name="submissions_create"),
    path("submissions/cohort/<int:cohort_id>", cohort_submissions_page, name="cohort_submissions"),
    path("submissions/cohort/<int:cohort_id>/create", submission_create_page, name="submission_create_for_cohort"),
    path("submissions/<int:submission_id>", submission_detail_page, name="submission_detail"),
    path("submissions/<int:submission_id>/save-final-comments", save_submission_final_comments, name="save_submission_final_comments"),
    path("submissions/<int:submission_id>/<str:table_name>", submission_table_manage, name="submission_table_manage"),
    path(
        "submissions/<int:submission_id>/<str:table_name>/files/<int:file_id>/revalidate",
        revalidate_submission_file,
        name="submission_revalidate_file",
    ),
    path(
        "submissions/<int:submission_id>/<str:table_name>/variables/<int:variable_id>/revalidate",
        revalidate_submission_variable,
        name="submission_revalidate_variable",
    ),
    path(
        "submissions/<int:submission_id>/<str:table_name>/validation/<int:validation_run_id>",
        submission_validation_status,
        name="submission_validation_status",
    ),
    path(
        "submissions/<int:submission_id>/<str:table_name>/validation/<int:validation_run_id>/json",
        submission_validation_status_json,
        name="submission_validation_status_json",
    ),
    path("submissions/<int:submission_id>/tables/<int:table_id>/validation-csv", download_patient_validation_csv, name="download_patient_validation_csv"),
    path("submissions/<int:submission_id>/tables/<int:table_id>/files/<int:file_id>/validation-csv", download_file_patient_validation_csv, name="download_file_patient_validation_csv"),
    path("submissions/<int:submission_id>/tables/<int:table_id>/files/<int:file_id>/mark-failed", mark_file_failed, name="mark_file_failed"),
    path("submissions/<int:submission_id>/tables/<int:table_id>/files/<int:file_id>/retry", retry_file_processing, name="retry_file_processing"),
    path("submissions/upload", submissions_upload_page, name="submissions.upload"),
    path("submissions/<int:submission_id>/upload", submissions_upload_page, name="submissions_upload"),
    path("cohorts", cohorts_page, name="cohorts"),
    path("cohorts/<int:cohort_id>", cohort_detail, name="cohort_detail"),
    path("dashboard", dashboard_page, name="dashboard"),
    path("account", account_page, name="account"),
    path("sign-out", signout_view, name="auth.sign_out"),
    path("sign-in", anonymous_required(sign_in_page), name="auth.sign_in"),
    
    # Ajax paths
    path("upload/temp", upload_temp_file, name="upload_temp_file"),
    # Attachment paths
    path("submissions/<int:submission_id>/<str:table_name>/attachments/upload", upload_attachment, name="upload_attachment"),
    path("submissions/<int:submission_id>/<str:table_name>/attachments/upload-secure", upload_attachment_secure, name="upload_attachment_secure"),
    path("submissions/<int:submission_id>/attachments/upload-secure", upload_submission_attachment_secure, name="upload_submission_attachment_secure"),
    path("attachments/<int:attachment_id>/download", download_attachment, name="download_attachment"),
    path("attachments/<int:attachment_id>/remove/", remove_attachment, name="remove_attachment"),
    # Review API paths (following existing AJAX pattern without /api/ prefix)
    path("tables/<int:table_id>/toggle-review", toggle_table_review, name="toggle_table_review"),
    path("tables/<int:table_id>/save-comments", save_table_comments, name="save_table_comments"),
    path("files/<int:file_id>/save-comments", save_file_comments, name="save_file_comments"),
    path("files/<int:file_id>/save-name", save_file_name, name="save_file_name"),
    path("attachments/<int:attachment_id>/save-name", save_attachment_name, name="save_attachment_name"),
    path("attachments/<int:attachment_id>/save-comments", save_attachment_comments, name="save_attachment_comments"),
    path("attachments/<int:attachment_id>/delete", delete_attachment, name="delete_attachment"),
    path("tables/<int:table_id>/track-report-view", track_report_view, name="track_report_view"),
    path("tables/<int:table_id>/review-status", get_table_review_status, name="get_table_review_status"),

    # Internal Storage API (services server only)
    path("internal/storage/upload", storage_upload, name="internal_storage_upload"),
    path("internal/storage/upload_chunked", storage_upload_chunked, name="internal_storage_upload_chunked"),
    path("internal/storage/download", storage_download, name="internal_storage_download"),
    path("internal/storage/delete", storage_delete, name="internal_storage_delete"),
    path("internal/storage/delete_prefix", storage_delete_prefix, name="internal_storage_delete_prefix"),
    path("internal/storage/list", storage_list, name="internal_storage_list"),
    path("internal/storage/exists", storage_exists, name="internal_storage_exists"),
    path("internal/storage/metadata", storage_metadata, name="internal_storage_metadata"),
    path("internal/storage/cleanup", cleanup_scratch, name="internal_cleanup_scratch"),
    path("internal/storage/health", storage_health, name="internal_storage_health"),
    
    # Admin
    path("admin/", admin.site.urls),
]

# Add SAML URLs based on configuration
if not getattr(settings, 'DISABLE_SAML', False) and (getattr(settings, 'USE_DOCKER_SAML', False) or not settings.DEBUG):
    # Real SAML2 authentication endpoints
    urlpatterns += [
        # Override the login to use ForceAuthn
        path('saml2/login/', saml_login_force_auth, name='saml2_login'),
        # Include other djangosaml2 URLs
        path('saml2/', include('djangosaml2.urls')),
    ]
elif getattr(settings, 'USE_MOCK_SAML', False):
    # Mock SAML/Shibboleth endpoints (development only)
    urlpatterns += [
        path("auth/saml/login", MockSAMLLogin.as_view(), name="saml2_login"),
        path("auth/mock-idp/login", MockIdPLogin.as_view(), name="mock_idp_login"),
        path("auth/saml/acs", MockSAMLACS.as_view(), name="mock_saml_acs"),
        path("auth/saml/metadata", MockSAMLMetadata.as_view(), name="mock_saml_metadata"),
        path("auth/saml/logout", MockSAMLLogout.as_view(), name="mock_saml_logout"),
    ]
