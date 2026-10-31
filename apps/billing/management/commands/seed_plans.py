"""Management command: seed the billing plan table with Free and Plus plans.

Usage:
    python manage.py seed_plans
    python manage.py seed_plans --update   # update existing records

Run once after first deploy and whenever plan details change.
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
            "pantry",
            "save_recipes_limited",  # up to 20
            "community_submissions",
        ],
    },
    {
        "code": "plus",
        "name": "Flavor Find Plus",
        "price_kes": "199.00",
        "features": [
            "search",
            "dish_pages",
            "regions",
            "pantry",
            "save_recipes_unlimited",
            "community_submissions",
            "meal_plans",
            "shopping_lists",
            "nutrition_details",
            "budget_mode",
            "offline_sync",
            "no_ads",
        ],
    },
]


class Command(BaseCommand):
    help = "Seed the billing plan table with Free and Plus plans."

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
                self.stdout.write(self.style.SUCCESS(f"  Created plan: {code}"))
            else:
                updated_count += 1
                verb = "Updated" if update else "Skipped (already exists)"
                self.stdout.write(f"  {verb}: {code}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. Created: {created_count}, "
                f"{'Updated' if update else 'Skipped'}: {updated_count}"
            )
        )
