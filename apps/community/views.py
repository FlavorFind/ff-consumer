"""Community views — submissions and reviews."""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.community.models import Review, Submission
from apps.community.serializers import (
    CreateReviewSerializer,
    CreateSubmissionSerializer,
    ReviewSerializer,
    SubmissionSerializer,
)


class SubmissionListView(APIView):
    """List and create recipe submissions."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: SubmissionSerializer(many=True)},
        summary="List own submissions",
        description="Returns the current user's recipe submissions and their status.",
    )
    def get(self, request):
        submissions = Submission.objects.filter(user=request.user)
        return Response(SubmissionSerializer(submissions, many=True).data)

    @extend_schema(
        request=CreateSubmissionSerializer,
        responses={201: SubmissionSerializer},
        summary="Submit a recipe",
        description=(
            "Submit a recipe for review. The submission enters the moderation queue. "
            "After approval, a Celery worker forwards it to the engine."
        ),
    )
    def post(self, request):
        ser = CreateSubmissionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        submission = Submission.objects.create(
            user=request.user,
            payload=ser.validated_data,
            status=Submission.Status.DRAFT,
        )
        return Response(SubmissionSerializer(submission).data, status=status.HTTP_201_CREATED)


class SubmissionDetailView(APIView):
    """Get a single submission."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: SubmissionSerializer}, summary="Get submission detail")
    def get(self, request, submission_id):
        try:
            submission = Submission.objects.get(id=submission_id, user=request.user)
        except Submission.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(SubmissionSerializer(submission).data)


class DishReviewView(APIView):
    """List and create reviews for a dish."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: ReviewSerializer(many=True)},
        summary="List approved reviews for a dish",
    )
    def get(self, request, slug):
        reviews = Review.objects.filter(dish_slug=slug, status=Review.Status.APPROVED)
        return Response(ReviewSerializer(reviews, many=True).data)

    @extend_schema(
        request=CreateReviewSerializer,
        responses={201: ReviewSerializer},
        summary="Submit a review",
        description="Submit a star rating and review for a dish. Queued for moderation.",
    )
    def post(self, request, slug):
        # Need dish_id — get it from the engine
        try:
            from apps.engine_client.client import engine

            dish = engine.get_dish(slug=slug)
            dish_id = dish.get("id") or dish.get("dish_id", "")
        except Exception:
            dish_id = ""

        ser = CreateReviewSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        review, created = Review.objects.update_or_create(
            user=request.user,
            dish_id=dish_id or slug,  # fallback to slug if id unavailable
            defaults={
                "dish_slug": slug,
                "stars": ser.validated_data["stars"],
                "text": ser.validated_data.get("text", ""),
                "status": Review.Status.PENDING,
            },
        )
        return Response(
            ReviewSerializer(review).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
