from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required


@login_required
def index_page(request):
    # Redirect logged-in users to dashboard
    return redirect('dashboard')
