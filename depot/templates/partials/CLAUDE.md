# Validation Partials Component Standards

## Overview

Validation summary partials display statistical summaries for different data types (enum, date, numeric, ID, boolean). These templates follow consistent spacing and structural patterns to ensure visual harmony across all variable types.

## Required Structure

### 1. Container Wrapper

**All validation summary partials MUST use:**

```html
<div class="px-6 pt-3 pb-6 space-y-8 divide-y divide-gray-200">
    <!-- Sections here -->
</div>
```

**Breakdown:**
- `px-6`: Horizontal padding (24px) for content area
- `pt-3`: Top padding (12px) after section header
- `pb-6`: Bottom padding (24px) for spacing before next section
- `space-y-8`: Vertical spacing (32px) between sibling divs
- `divide-y divide-gray-200`: Horizontal dividers between sections

### 2. Section Wrapper

**Each logical section MUST use:**

```html
<div class="space-y-6 pb-8">
    <c-section-heading title="Section Title" caption="Section description." />
    <!-- Section content -->
</div>
```

**Breakdown:**
- `space-y-6`: Vertical spacing (24px) between heading and content
- `pb-8`: Bottom padding (32px) to create space before the divider

**Note:** If a section contains no divider-separated siblings, `pb-8` can be omitted on the last section.

### 3. Section Headings

**Use the `<c-section-heading>` component:**

```html
<c-section-heading
    title="Heading text"
    caption="Optional descriptive caption."
/>
```

**Props:**
- `title` (required): Main heading text
- `caption` (optional): Smaller descriptive text below title

### 4. Statistical Tables

**Use the `<c-stat-table>` component:**

```html
<c-stat-table
    class="mt-2"
    key_heading="Metric"
    value_heading="Value"
>
    <tr>
        <th scope="row" class="px-2.5 py-1 text-left font-medium text-gray-700">
            Row label
        </th>
        <td class="px-2.5 py-1.5 text-right text-gray-900 font-mono font-normal">
            {{ value }}
        </td>
    </tr>
</c-stat-table>
```

**Props:**
- `class="mt-2"`: Top margin (8px) for spacing after heading
- `key_heading`: Left column header text
- `value_heading`: Right column header text

**Row Structure:**
- `<th scope="row">`: Left column (labels) - left-aligned, medium weight
- `<td>`: Right column (values) - right-aligned, monospace font
- `px-2.5 py-1`: Cell padding for rows
- `py-1.5`: Slightly more vertical padding for data cells

### 5. Lists

**For bullet lists:**

```html
<ul class="list-disc list-inside space-y-0.5">
    <li>Item text</li>
</ul>
```

**Breakdown:**
- `list-disc`: Bullet point style
- `list-inside`: Bullets inside the list item box
- `space-y-0.5`: Minimal spacing (2px) between items

### 6. Charts

**For Plotly charts:**

```html
<div class="bg-white rounded-lg border border-gray-200 p-4">
    <div id="chart-{{ variable.id }}" style="width:100%;height:400px;"></div>
</div>
```

**Breakdown:**
- White background with rounded border
- `p-4`: Padding (16px) around chart
- Chart div: Full width, 400px height

## Spacing Hierarchy

**Summary of spacing values:**

| Element | Spacing Class | px Value | Purpose |
|---------|--------------|----------|---------|
| Container sections | `space-y-8` | 32px | Major section separation |
| Section children | `space-y-6` | 24px | Heading to content |
| Section bottom padding | `pb-8` | 32px | Space before divider |
| List items | `space-y-0.5` | 2px | Tight vertical rhythm |
| Component top margin | `mt-2` | 8px | After headings |

## Consistency Checklist

When creating or updating a validation summary partial:

- ✅ Container uses `px-6 pt-3 pb-6 space-y-8 divide-y divide-gray-200`
- ✅ Each section uses `space-y-6 pb-8`
- ✅ Section headings use `<c-section-heading>` component
- ✅ Statistical tables use `<c-stat-table>` component
- ✅ Lists use `list-disc list-inside space-y-0.5`
- ✅ Charts use white background with `p-4` padding
- ✅ No inline styles except for chart dimensions

## Examples

### Correct Section Structure

```html
<div class="px-6 pt-3 pb-6 space-y-8 divide-y divide-gray-200">
    <!-- Section 1 -->
    <div class="space-y-6 pb-8">
        <c-section-heading title="Summary metrics" caption="Basic statistics." />
        <c-stat-table class="mt-2" key_heading="Metric" value_heading="Value">
            <tr>
                <th scope="row" class="px-2.5 py-1 text-left font-medium text-gray-700">
                    Total values
                </th>
                <td class="px-2.5 py-1.5 text-right text-gray-900 font-mono font-normal">
                    {{ variable.total_rows }}
                </td>
            </tr>
        </c-stat-table>
    </div>

    <!-- Section 2 -->
    <div class="space-y-6 pb-8">
        <c-section-heading title="Distribution" caption="Value frequencies." />
        <!-- Content here -->
    </div>
</div>
```

### Incorrect Patterns to Avoid

```html
<!-- ❌ WRONG: Missing pb-6 on container -->
<div class="px-6 pt-3 space-y-8 divide-y divide-gray-200">

<!-- ❌ WRONG: Using space-y-8 instead of space-y-6 for sections -->
<div class="space-y-8 pb-8">

<!-- ❌ WRONG: Missing pb-8 on sections with siblings -->
<div class="space-y-6">

<!-- ❌ WRONG: Not using c-section-heading component -->
<h3 class="text-lg font-semibold">Title</h3>

<!-- ❌ WRONG: Not using c-stat-table component -->
<table class="w-full">
```

## File Inventory

Current validation summary partials (all compliant):

- ✅ `validation_summary_enum.html` - Follows all standards
- ✅ `validation_summary_date.html` - Follows all standards
- ✅ `validation_summary_boolean.html` - Follows all standards
- ✅ `validation_summary_id.html` - Follows all standards
- ✅ `validation_summary_numeric.html` - Follows all standards
