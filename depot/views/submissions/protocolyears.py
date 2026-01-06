from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from depot.models import ProtocolYear, CohortSubmission


@login_required
def protocol_years_page(request):
    # Get all protocol years with submission counts
    protocol_years_qs = ProtocolYear.objects.annotate(
        total_submissions=Count('cohort_submissions'),
        completed_submissions=Count(
            'cohort_submissions',
            filter=Q(cohort_submissions__status='signed_off')
        ),
        in_progress_submissions=Count(
            'cohort_submissions',
            filter=Q(cohort_submissions__status__in=['draft', 'in_progress', 'completed'])
        )
    ).order_by('-created_at')
    
    # Transform for template
    protocol_years = []
    for year in protocol_years_qs:
        # Determine status based on submissions
        if year.in_progress_submissions > 0:
            status = "Active"
        elif year.total_submissions == 0:
            status = "Not Started"
        elif year.completed_submissions == year.total_submissions:
            status = "Completed"
        else:
            status = "Inactive"
            
        protocol_years.append({
            "id": year.id,
            "name": year.name,
            "status": status,
            "total_submissions": year.total_submissions,
            "completed_submissions": year.completed_submissions,
            "in_progress_submissions": year.in_progress_submissions,
        })

    return render(
        request,
        "pages/submissions/protocolyears.html",
        {
            "title": "Protocol Years",
            "protocol_years": protocol_years,
        },
    )