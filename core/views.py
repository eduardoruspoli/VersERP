from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import redirect, render

# Create your views here.

@login_required
def dashboard(request):
    return render(
        request,
        "core/dashboard.html",
    ) 

def login_view(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")

    if request.method == "POST":
        form = AuthenticationForm(
            request,
            data=request.POST,
        )

        if form.is_valid():
            usuario = form.get_user()
            login(request, usuario)

            proxima_url = request.GET.get("next")

            if proxima_url:
                return redirect(proxima_url)

            return redirect("core:dashboard")

    else:
        form = AuthenticationForm(request)

    return render(
        request,
        "core/login.html",
        {
            "form": form,
        },
    )


def logout_view(request):
    if request.method == "POST":
        logout(request)

    return redirect("core:login")