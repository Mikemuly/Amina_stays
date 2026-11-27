from django.contrib import admin

from .models import C2BTransaction, CreditNote, Invoice, Payment, Refund

admin.site.register(Payment)
admin.site.register(Refund)
admin.site.register(C2BTransaction)
admin.site.register(Invoice)
admin.site.register(CreditNote)
