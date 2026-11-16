"""Management command: seed the billing plan table.

Tiers:
  free     — KES 0
  plus     — KES 499/month
  premium  — KES 999/month

Usage:
    python manage.py seed_plans            # create if missing
    python manage.py seed_plans --update   # update existing records too
"""

from django.core.management.base import BaseCommand

from apps.billing.models import Plan

PLANS = [
    {
        "code": "free",
        "name": "Free",
        "price_kes": "0.00",
        "features": [
            "search",
            "dish_pages",
            "regions",
            "pantry_basic",          # pantry without quantity tracking
            "save_recipes_limited",  # up to 20
            "community_submissions",
        ],
    },
    {
        "code": "plus",
        "name": "Flavor Find Plus",
        "price_kes": "499.00",
        "features": [
            "search",
            "dish_pages",
            "regions",
            "pantry_basic",
            "pantry_quantity",        # quantity + unit + low-stock threshold
            "can_make",               # "dishes I can make" from pantry
            "save_recipes_unlimited",
            "community_submissions",
            "meal_plans",
            "shopping_lists",
            "pantry_deduction",       # auto-deduct from pantry when shopping checked
            "buy_reminders",          # pre-cook buy-ahead notifications
            "nutrition_details",
            "budget_mode",
            "no_ads",
        ],
    },
    {
        "code": "premium",
        "name": "Flavor Find Premium",
        "price_kes": "999.00",
        "features": [
            "search",
            "dish_pages",
            "regions",
            "pantry_basic",
            "pantry_quantity",
            "can_make",
            "save_recipes_unlimited",
            "community_submissions",
            "meal_plans",
            "shopping_lists",
            "pantry_deduction",
            "buy_reminders",
            "nutrition_details",
            "budget_mode",
            "no_ads",
            "priority_search",        # boosted ranking in search results
            "offline_sync",           # full offline recipe cache
            "advanced_analytics",     # cooking history, nutrition summaries
            "early_access",           # new features before public release
        ],
    },
]


class Command(BaseCommand):
    help = "Seed billing plans (Free / Plus KES 499 / Premium KES 999)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--update",
            action="store_true",
            help="Update existing plan records (default: skip if already exists).",
        )

    def handle(self, *args, **options):
        update = options["update"]
        created_count = 0
        updated_count = 0

        for plan_data in PLANS:
            code = plan_data["code"]
            if update:
                _, created = Plan.objects.update_or_create(
                    code=code,
                    defaults={
                        "name": plan_data["name"],
                        "price_kes": plan_data["price_kes"],
                        "features": plan_data["features"],
                    },
                )
            else:
                _, created = Plan.objects.get_or_create(
                    code=code,
                    defaults={
                        "name": plan_data["name"],
                        "price_kes": plan_data["price_kes"],
                        "features": plan_data["features"],
                    },
                )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(
                    f"  Created: {code} — KES {plan_data['price_kes']}/month"
                ))
            else:
                updated_count += 1
                verb = "Updated" if update else "Skipped (already exists)"
                self.stdout.write(f"  {verb}: {code}")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. Created: {created_count}, "
            f"{'Updated' if update else 'Skipped'}: {updated_count}"
        ))
