from django.urls import path
from . import views as v

urlpatterns = [
    path('slips/', v.SlipListView.as_view(), name='payroll-slips'),
    path('slips/generate/', v.SlipGenerateView.as_view(), name='payroll-generate'),
    path('slips/<int:pk>/', v.SlipDetailView.as_view(), name='payroll-slip'),
    path('slips/<int:pk>/pay/', v.SlipPayView.as_view(), name='payroll-pay'),
    path('slips/<int:pk>/unpay/', v.SlipUnpayView.as_view(), name='payroll-unpay'),
    path('advances/', v.AdvanceListView.as_view(), name='payroll-advances'),
    path('advances/<int:pk>/', v.AdvanceDetailView.as_view(), name='payroll-advance'),
    path('staff/', v.StaffOptionsView.as_view(), name='payroll-staff'),
    path('report/', v.ReportView.as_view(), name='payroll-report'),
]
