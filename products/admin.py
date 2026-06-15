from django.contrib import admin

from .models import Marketplace, Offer, PriceSnapshot, RAMModule


@admin.register(Marketplace)
class MarketplaceAdmin(admin.ModelAdmin):
    list_display = ('name', 'url', 'is_active')
    list_editable = ('is_active',)


class PriceSnapshotInline(admin.TabularInline):
    model = PriceSnapshot
    extra = 0
    readonly_fields = ('price', 'is_available', 'scraped_at')
    can_delete = False
    ordering = ('-scraped_at',)


class OfferInline(admin.TabularInline):
    model = Offer
    extra = 0
    readonly_fields = ('marketplace', 'external_id', 'name', 'url', 'last_updated')
    can_delete = False
    show_change_link = True


@admin.register(RAMModule)
class RAMModuleAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'brand', 'part_number', 'capacity_gb', 'memory_type',
        'frequency_mhz', 'offers_count', 'latest_price',
    )
    list_filter = ('brand', 'memory_type', 'capacity_gb')
    search_fields = ('name', 'brand', 'part_number')
    inlines = [OfferInline]


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ('name', 'marketplace', 'ram_module', 'latest_price', 'last_updated')
    list_filter = ('marketplace',)
    search_fields = ('name', 'external_id', 'ram_module__name')
    inlines = [PriceSnapshotInline]


@admin.register(PriceSnapshot)
class PriceSnapshotAdmin(admin.ModelAdmin):
    list_display = ('offer', 'price', 'is_available', 'scraped_at')
    list_filter = ('is_available', 'scraped_at')
    search_fields = ('offer__name',)
