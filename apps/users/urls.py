from django.urls import path

from apps.users import views

app_name = "users"
urlpatterns = [
    path("profile/", views.ProfileView.as_view(), name="user_profile"),
    path("profile/upload-image/", views.UploadProfileImageView.as_view(), name="upload_profile_image"),
    path("connected-accounts/", views.ConnectedAccountsView.as_view(), name="connected_accounts"),
]
