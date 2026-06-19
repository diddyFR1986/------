from django.urls import path

from . import views

app_name = 'products'

urlpatterns = [
    path('', views.product_list, name='product_list'),
    path('product/<int:pk>/', views.product_detail, name='product_detail'),
    path('compare/', views.compare, name='compare'),
    path('compare/toggle/<int:pk>/', views.compare_toggle,
         name='compare_toggle'),
    path('compare/clear/', views.compare_clear, name='compare_clear'),
    path('compare/remove/<int:pk>/', views.compare_remove,
         name='compare_remove'),
    path('scrape/', views.trigger_scrape, name='trigger_scrape'),
]
