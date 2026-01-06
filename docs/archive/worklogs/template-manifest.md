# Template Manifest - NA-ACCORD Data Depot

## URL -> View -> Template Mapping

| URL Pattern | View Function | Template | Status |
|------------|---------------|----------|--------|
| `/` | `index_page` | `pages/index.html` | ✅ Active |
| `/audit` | `audit_page` | `pages/audit.html` | ✅ Active |
| `/audit/upload` | `audit_upload` | Unknown | ❓ Check |
| `/audit/reports/<id>` | `audit_status` | `pages/audit_status.html` | ✅ Active |
| `/notebooks/<id>/view` | `notebook_view` | Unknown | ❓ Check |
| `/submissions` | `submissions_page` | `pages/submissions/index.html` | ✅ Active |
| `/protocol-years` | `protocol_years_page` | `pages/submissions/protocolyears.html` | ✅ Active |
| `/submissions/create` | `submission_create_page` | `pages/submissions/create.html` | ✅ Active |
| `/submissions/cohort/<id>` | `cohort_submissions_page` | `pages/submissions/cohort_submissions.html` | ✅ Active |
| `/submissions/<id>` | `submission_detail_page` | `pages/submissions/detail.html` | ✅ Active |
| `/submissions/<id>/<table>` | `submission_table_manage` | `pages/submissions/table_manage.html` | ✅ Active |
| `/submissions/upload` | `submissions_upload_page` | `pages/submissions/upload.html` | ✅ Active |
| `/cohorts` | `cohorts_page` | `pages/cohorts.html` | ✅ Active |
| `/dashboard` | `dashboard_page` | `pages/dashboard.html` | ✅ Active |
| `/account` | `account_page` | `pages/account.html` | ✅ Active |
| `/sign-in` | `sign_in_page` | `pages/auth/sign_in.html` | ✅ Active |
| `/sign-out` | `signout_view` | No template (redirect) | N/A |
| `/upload/temp` | `upload_temp_file` | No template (AJAX) | N/A |

## Template Directory Structure

### Pages (Main Templates)
- ✅ `pages/index.html` - Homepage
- ✅ `pages/account.html` - User account page
- ✅ `pages/audit.html` - Audit page
- ❓ `pages/audit_modern.html` - Modern audit page (possibly unused)
- ✅ `pages/audit_status.html` - Audit status page
- ✅ `pages/cohorts.html` - Cohorts listing
- ✅ `pages/dashboard.html` - Dashboard
- ✅ `pages/auth/sign_in.html` - Sign in page

### Submission Pages
- ✅ `pages/submissions/index.html` - Submissions listing
- ✅ `pages/submissions/create.html` - Create submission
- ✅ `pages/submissions/detail.html` - Submission details
- ✅ `pages/submissions/cohort_submissions.html` - Cohort submissions
- ✅ `pages/submissions/protocolyears.html` - Protocol years
- ✅ `pages/submissions/table_manage.html` - Table management
- ✅ `pages/submissions/upload.html` - Upload page
- ❓ `pages/submissions/file_manage.html` - File management (possibly replaced by table_manage)

### Layouts
- ✅ `layouts/app.html` - Main application layout

### Partials
- ✅ `partials/footer.html` - Footer partial
- ✅ `partials/mobile_nav.html` - Mobile navigation
- ✅ `partials/nav.html` - Main navigation
- ✅ `partials/scripts.html` - JavaScript includes

### Depot Specific
- ❓ `depot/audit_status.html` - Duplicate of pages/audit_status.html?

## Cotton Components (Already Created)

### Layout Components
- ✅ `c-app_page` - Application page wrapper
- ✅ `c-card` - Card container
- ✅ `c-page_container` - Page container
- ✅ `c-breadcrumbs` - Breadcrumb navigation
- ✅ `c-breadcrumb_item` - Individual breadcrumb

### Form Components
- ✅ `c-input` - Text input field
- ✅ `c-input/text` - Text input variant
- ✅ `c-input/search` - Search input variant
- ✅ `c-textarea` - Textarea field
- ✅ `c-checkbox` - Checkbox input
- ✅ `c-radio` - Radio button
- ✅ `c-label` - Form label

### UI Components
- ✅ `c-button` - Button component
- ✅ `c-async_button` - Async button with loading state
- ✅ `c-badge` - Badge/tag component
- ✅ `c-status_badge` - Status indicator badge
- ✅ `c-icon` - Icon wrapper
- ✅ `c-heading` - Heading component
- ✅ `c-loading` - Loading indicator
- ✅ `c-error` - Error message display
- ✅ `c-toast` - Toast notification

### Data Components
- ✅ `c-data_table` - Data table wrapper
- ✅ `c-data_row` - Table row component

### Upload Components
- ✅ `c-file_upload` - File upload component (comprehensive)
- ✅ `c-upload_box` - Upload dropzone

## Templates Using Cotton Components

### High Adoption (using multiple components)
- `pages/submissions/detail.html`
- `pages/submissions/table_manage.html`
- `pages/submissions/index.html`

### Partial Adoption
- `pages/submissions/file_manage.html`
- `pages/submissions/protocolyears.html`

### Not Yet Using Components
- `pages/index.html`
- `pages/account.html`
- `pages/audit.html`
- `pages/cohorts.html`
- `pages/dashboard.html`
- `pages/auth/sign_in.html`

## Identified Dead/Duplicate Templates

### Likely Unused
- ❓ `pages/audit_modern.html` - Check if referenced anywhere
- ❓ `depot/audit_status.html` - Appears to be duplicate
- ❓ `pages/submissions/file_manage.html` - May be replaced by table_manage

## Common Patterns Needing Components

### Form Patterns (found in multiple templates)
```html
<!-- Common form field pattern -->
<div class="mb-4">
    <label class="block text-sm font-medium text-gray-700">
    <input type="text" class="mt-1 block w-full rounded-md border-gray-300">
    <p class="mt-1 text-sm text-red-600">Error message</p>
</div>
```

### Table Patterns
```html
<!-- Common table structure -->
<table class="min-w-full divide-y divide-gray-200">
    <thead class="bg-gray-50">
    <tbody class="bg-white divide-y divide-gray-200">
</table>
```

### Card Patterns
```html
<!-- Common card layout -->
<div class="bg-white overflow-hidden shadow rounded-lg">
    <div class="px-4 py-5 sm:p-6">
</div>
```

## Recommendations for New Components

### Priority 1 - Form Enhancement
- [ ] `c-form_group` - Wrapper for form fields with label/error
- [ ] `c-select` - Select dropdown component
- [ ] `c-field_error` - Field error message component

### Priority 2 - Layout Components
- [ ] `c-page_header` - Standardized page header
- [ ] `c-section` - Content section wrapper
- [ ] `c-empty_state` - Empty state message

### Priority 3 - Data Display
- [ ] `c-pagination` - Pagination component
- [ ] `c-sort_header` - Sortable table header
- [ ] `c-filter_bar` - Filter controls bar

### Priority 4 - Submission Specific
- [ ] `c-submission_card` - Submission summary card
- [ ] `c-file_status` - File upload status indicator
- [ ] `c-audit_report` - Audit report display

## Next Steps

1. **Verify Dead Templates**: Check if templates marked with ❓ are actually used
2. **Component Migration**: Start with high-traffic templates (submissions/*)
3. **Create Missing Components**: Focus on form components first
4. **Standardize Patterns**: Replace inline styles with component classes
5. **Remove Duplicates**: Clean up confirmed dead templates