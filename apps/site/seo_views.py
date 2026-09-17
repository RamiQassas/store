import xml.sax.saxutils as saxutils
from django.http import HttpResponse
from django.shortcuts import render
from django.core.cache import cache
from django.utils import timezone
from apps.catalog.models import Product, Category


def _xml_escape(text):
    if not text:
        return ""
    return saxutils.escape(str(text), {'"': "&quot;", "'": "&apos;"})


def sitemap_xml_view(request):
    """
    High-performance dynamic XML sitemap for Googlebot and search engines.
    Features:
    - Cached in LocMemCache/Redis for 30 minutes.
    - Includes core site pages, active categories, and active products.
    - Includes Google image extension (<image:image>) for rich image indexing.
    - Adapts dynamically to current store domain / tenant.
    """
    host = request.get_host()
    scheme = "https" if (request.is_secure() or request.headers.get("X-Forwarded-Proto") == "https") else "http"
    base_url = f"{scheme}://{host}"
    
    store = getattr(request, "store", None)
    cache_key = f"sitemap_xml_{getattr(store, 'id', 'global')}_{host}"
    cached_xml = cache.get(cache_key)
    if cached_xml:
        return HttpResponse(cached_xml, content_type="application/xml; charset=utf-8")

    now_date = timezone.now().strftime("%Y-%m-%d")
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">',
    ]

    # 1. Core Static Pages
    static_pages = [
        ("/", "1.0", "hourly"),
        ("/catalog/", "0.9", "hourly"),
        ("/stores/", "0.7", "daily"),
        ("/contact/", "0.5", "monthly"),
        ("/privacy-policy/", "0.3", "monthly"),
        ("/terms-of-service/", "0.3", "monthly"),
        ("/refund-policy/", "0.3", "monthly"),
    ]

    for path, priority, changefreq in static_pages:
        xml_lines.append(
            f"  <url>\n"
            f"    <loc>{base_url}{path}</loc>\n"
            f"    <lastmod>{now_date}</lastmod>\n"
            f"    <changefreq>{changefreq}</changefreq>\n"
            f"    <priority>{priority}</priority>\n"
            f"  </url>"
        )

    # 2. Active Categories
    if store:
        categories = Category.objects.filter(store=store, is_active=True).order_by("sort_order", "name")
    else:
        categories = Category.objects.filter(is_active=True).order_by("sort_order", "name")

    for cat in categories[:100]:
        cat_url = f"{base_url}/catalog/?category={cat.id}"
        img_xml = ""
        if cat.image:
            img_url = f"{base_url}{cat.image.url}"
            img_xml = (
                f"    <image:image>\n"
                f"      <image:loc>{_xml_escape(img_url)}</image:loc>\n"
                f"      <image:title>{_xml_escape(cat.name)}</image:title>\n"
                f"    </image:image>\n"
            )
        xml_lines.append(
            f"  <url>\n"
            f"    <loc>{_xml_escape(cat_url)}</loc>\n"
            f"    <lastmod>{now_date}</lastmod>\n"
            f"    <changefreq>daily</changefreq>\n"
            f"    <priority>0.8</priority>\n"
            f"{img_xml}"
            f"  </url>"
        )

    # 3. Active Products
    if store:
        products = Product.objects.filter(store=store, is_active=True).select_related("category")
    else:
        products = Product.objects.filter(is_active=True).select_related("category")

    for p in products.order_by("-updated_at")[:1500]:
        p_url = f"{base_url}/catalog/{p.id}/"
        p_lastmod = p.updated_at.strftime("%Y-%m-%d") if getattr(p, "updated_at", None) else now_date
        
        img_xml = ""
        if p.image:
            img_url = f"{base_url}{p.image.url}"
            img_xml = (
                f"    <image:image>\n"
                f"      <image:loc>{_xml_escape(img_url)}</image:loc>\n"
                f"      <image:title>{_xml_escape(p.name)}</image:title>\n"
                f"    </image:image>\n"
            )
        
        xml_lines.append(
            f"  <url>\n"
            f"    <loc>{_xml_escape(p_url)}</loc>\n"
            f"    <lastmod>{p_lastmod}</lastmod>\n"
            f"    <changefreq>daily</changefreq>\n"
            f"    <priority>0.8</priority>\n"
            f"{img_xml}"
            f"  </url>"
        )

    xml_lines.append("</urlset>")
    full_xml = "\n".join(xml_lines)

    cache.set(cache_key, full_xml, 1800)
    return HttpResponse(full_xml, content_type="application/xml; charset=utf-8")


def custom_404_view(request, exception=None):
    """
    Renders an elegant, branded 404 page in Arabic with store search and navigation.
    Returns standard HTTP 404 status code for SEO compliance.
    """
    return render(request, "404.html", {
        "status_code": 404,
        "exception": str(exception) if exception else "",
    }, status=404)


def custom_500_view(request):
    """
    Renders a graceful 500 error page.
    """
    return render(request, "500.html", {
        "status_code": 500,
    }, status=500)
