from django.http import HttpResponseRedirect
from django.contrib.auth import logout
from django.urls import reverse


def signout_view(request):
    logout(request)
    return HttpResponseRedirect(reverse("auth.sign_in"))
