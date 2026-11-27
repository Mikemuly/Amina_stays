from django.contrib import admin

from .models import Amenity, Area, CalendarBlock, ICalFeed, PriceOverride, PriceRule, Unit, UnitPhoto, Wishlist

admin.site.register(Area)
admin.site.register(Amenity)
admin.site.register(Unit)
admin.site.register(UnitPhoto)
admin.site.register(PriceRule)
admin.site.register(PriceOverride)
admin.site.register(CalendarBlock)
admin.site.register(ICalFeed)
admin.site.register(Wishlist)
