from django.urls import path

from .views import FollowersListView, FollowingListView, FollowToggleView

urlpatterns = [
    path("<int:user_id>/toggle/", FollowToggleView.as_view(), name="follow-toggle"),
    path("<int:user_id>/followers/", FollowersListView.as_view(), name="followers-list"),
    path("<int:user_id>/following/", FollowingListView.as_view(), name="following-list"),
]
