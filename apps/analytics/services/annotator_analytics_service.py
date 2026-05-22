from datetime import timedelta

from django.db.models import Avg, Count, IntegerField, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from apps.processing.models import Annotation, TaskAssignment, TaskAssignmentStatusChoices
from apps.scoring.models import ScoreLog, UserScore, ScoreActionTypeChoices


class AnnotatorAnalyticsService:
    def __init__(self, user):
        self.user = user
        now = timezone.now()
        self.now = now
        self.current_week_start = now - timedelta(days=6)
        self.previous_week_start = self.current_week_start - timedelta(days=7)
        self.previous_week_end = self.current_week_start - timedelta(seconds=1)
        self.current_month_start = now - timedelta(days=29)
        self.previous_month_start = self.current_month_start - timedelta(days=30)
        self.previous_month_end = self.current_month_start - timedelta(seconds=1)

    def _pct_change(self, current, previous):
        if previous in (None, 0):
            if current:
                return 100.0
            return 0.0
        return round(((current - previous) / previous) * 100.0, 1)

    def _format_signed(self, value):
        rounded = round(value, 1)
        sign = "+" if rounded >= 0 else ""
        return f"{sign}{rounded}%"

    def _format_duration(self, total_seconds):
        if total_seconds < 60:
            return f"{int(round(total_seconds))}s"
        return f"{int(round(total_seconds / 60.0))}m"

    def _calculate_consensus_match_rate(self, period_start, period_end=None):
        filters = {"user": self.user, "created_at__gte": period_start}
        if period_end:
            filters["created_at__lte"] = period_end

        match_count = ScoreLog.objects.filter(
            **filters,
            action_type=ScoreActionTypeChoices.ANNOTATION_MATCH_CONSENSUS,
        ).count()
        below_count = ScoreLog.objects.filter(
            **filters,
            action_type=ScoreActionTypeChoices.ANNOTATION_BELOW_THRESHOLD,
        ).count()

        total = match_count + below_count
        if total == 0:
            return 0.0
        return round((match_count / total) * 100.0, 1)

    def get_overview(self):
        user_score, _ = UserScore.objects.get_or_create(user=self.user)

        completed_assignments = TaskAssignment.objects.filter(
            annotator=self.user,
            status=TaskAssignmentStatusChoices.SUBMITTED,
        )
        total_tasks_completed = completed_assignments.count()

        current_week_tasks = completed_assignments.filter(completed_at__gte=self.current_week_start).count()
        previous_week_tasks = completed_assignments.filter(
            completed_at__gte=self.previous_week_start,
            completed_at__lte=self.previous_week_end,
        ).count()

        score_logs = ScoreLog.objects.filter(user=self.user)
        lifetime_points = int(user_score.total_points)

        current_performance = self._calculate_consensus_match_rate(self.current_month_start)
        previous_performance = self._calculate_consensus_match_rate(self.previous_month_start, self.previous_month_end)

        current_month_points = score_logs.filter(created_at__gte=self.current_month_start).aggregate(
            points=Coalesce(Sum("points"), Value(0), output_field=IntegerField())
        )["points"]
        previous_month_points = score_logs.filter(
            created_at__gte=self.previous_month_start,
            created_at__lte=self.previous_month_end,
        ).aggregate(points=Coalesce(Sum("points"), Value(0), output_field=IntegerField()))["points"]

        current_month_avg_points = score_logs.filter(created_at__gte=self.current_month_start).aggregate(
            avg_points=Avg("points")
        )["avg_points"] or 0.0
        previous_month_avg_points = score_logs.filter(
            created_at__gte=self.previous_month_start,
            created_at__lte=self.previous_month_end,
        ).aggregate(avg_points=Avg("points"))["avg_points"] or 0.0

        avg_time_seconds = (
            Annotation.objects.filter(annotator=self.user, time_spent_seconds__isnull=False, is_skipped=False).aggregate(
                avg_time=Avg("time_spent_seconds")
            )["avg_time"]
            or 0.0
        )
        avg_time_minutes = round(avg_time_seconds / 60.0, 1)

        cards = [
            {
                "key": "overall_performance",
                "label": "Overall performance",
                "value": current_performance,
                "display_value": f"{current_performance}%",
                "delta": {
                    "value": current_performance - previous_performance,
                    "label": "from last month",
                },
            },
            {
                "key": "tasks_completed",
                "label": "Tasks Completed",
                "value": total_tasks_completed,
                "display_value": str(total_tasks_completed),
                "delta": {
                    "value": current_week_tasks - previous_week_tasks,
                    "label": "this week",
                },
            },
            {
                "key": "points_earned",
                "label": "Points Earned",
                "value": int(current_month_points),
                "display_value": f"{int(current_month_points):,}",
                "delta": {
                    "value": self._pct_change(current_month_points, previous_month_points),
                    "label": "from last month",
                },
            },
            {
                "key": "avg_time_per_task",
                "label": "Avg. Time / Task",
                "value": avg_time_minutes,
                "display_value": self._format_duration(avg_time_seconds),
                "delta": None,
            },
        ]

        weekly_rows = (
            completed_assignments.filter(completed_at__gte=self.current_week_start)
            .annotate(period=TruncDate("completed_at"))
            .values("period")
            .annotate(tasks_completed=Count("id"))
            .order_by("period")
        )
        points_week_rows = (
            score_logs.filter(created_at__gte=self.current_week_start)
            .annotate(period=TruncDate("created_at"))
            .values("period")
            .annotate(points_earned=Coalesce(Sum("points"), Value(0), output_field=IntegerField()))
            .order_by("period")
        )
        points_by_day = {str(row["period"]): int(row["points_earned"]) for row in points_week_rows}

        weekly_performance = []
        for row in weekly_rows:
            day = str(row["period"])
            weekly_performance.append(
                {
                    "period": day,
                    "tasks_completed": int(row["tasks_completed"]),
                    "points_earned": points_by_day.get(day, 0),
                }
            )

        confidence_distribution_qs = (
            Annotation.objects.filter(annotator=self.user)
            .values("confidence")
            .annotate(value=Count("id"))
            .order_by("confidence")
        )
        confidence_distribution = [
            {"label": row["confidence"], "value": int(row["value"])} for row in confidence_distribution_qs
        ]

        readability_distribution_qs = (
            Annotation.objects.filter(annotator=self.user)
            .values("readability")
            .annotate(value=Count("id"))
            .order_by("readability")
        )
        readability_distribution = [
            {"label": row["readability"], "value": int(row["value"])} for row in readability_distribution_qs
        ]

        avg_time_trend_qs = (
            Annotation.objects.filter(
                annotator=self.user,
                created_at__gte=self.current_week_start,
                time_spent_seconds__isnull=False,
                is_skipped=False,
            )
            .annotate(period=TruncDate("created_at"))
            .values("period")
            .annotate(avg_time_seconds=Avg("time_spent_seconds"))
            .order_by("period")
        )
        avg_time_trend = [
            {
                "period": str(row["period"]),
                "avg_time_minutes": round((row["avg_time_seconds"] or 0.0) / 60.0, 2),
            }
            for row in avg_time_trend_qs
        ]

        graphs = {
            "weekly_performance": weekly_performance,
            "confidence_distribution": confidence_distribution,
            "readability_distribution": readability_distribution,
            "avg_time_trend": avg_time_trend,
        }

        for card in cards:
            delta = card.get("delta")
            if delta and card["key"] in ("overall_performance", "points_earned"):
                delta["label"] = f"{self._format_signed(delta['value'])} {delta['label']}"
            elif delta and card["key"] == "tasks_completed":
                sign = "+" if delta["value"] >= 0 else ""
                delta["label"] = f"{sign}{int(delta['value'])} {delta['label']}"

        return {
            "cards": cards,
            "graphs": graphs,
            "meta": {
                "lifetime_points": lifetime_points,
            },
        }

    def _calculate_current_streak(self):
        annotations = (
            Annotation.objects.filter(annotator=self.user)
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .order_by("-day")
            .distinct()
        )

        streak = 0
        current_date = timezone.now().date()

        for annotation in annotations:
            day = annotation["day"]
            expected_date = current_date - timedelta(days=streak)
            if day == expected_date:
                streak += 1
            else:
                break

        return streak

    def get_dashboard(self):
        user_score, _ = UserScore.objects.get_or_create(user=self.user)

        completed_tasks = TaskAssignment.objects.filter(
            annotator=self.user,
            status=TaskAssignmentStatusChoices.SUBMITTED,
        ).count()

        assigned_tasks = TaskAssignment.objects.filter(annotator=self.user).count()

        current_accuracy = self._calculate_consensus_match_rate(self.now - timedelta(days=365))

        total_points = int(user_score.total_points)

        current_streak = self._calculate_current_streak()

        highlights = [
            {
                "key": "tasks_completed",
                "label": "Tasks Completed",
                "value": completed_tasks,
                "display_value": str(completed_tasks),
            },
            {
                "key": "accuracy",
                "label": "Accuracy",
                "value": current_accuracy,
                "display_value": f"{current_accuracy}%",
            },
            {
                "key": "current_streak",
                "label": "Current Streak",
                "value": current_streak,
                "display_value": f"{current_streak} days",
            },
            {
                "key": "total_points",
                "label": "Total Points",
                "value": total_points,
                "display_value": f"{total_points:,}",
            },
            {
                "key": "assigned_tasks",
                "label": "Assigned Tasks",
                "value": assigned_tasks,
                "display_value": str(assigned_tasks),
            },
        ]

        recent_task_assignments = (
            TaskAssignment.objects.filter(annotator=self.user)
            .select_related("task")
            .order_by("-assigned_at")[:5]
        )

        recent_activity = []
        for assignment in recent_task_assignments:
            recent_activity.append(
                {
                    "id": str(assignment.id),
                    "task_name": assignment.task.name,
                    "status": assignment.status,
                    "assigned_at": assignment.assigned_at.isoformat(),
                    "completed_at": assignment.completed_at.isoformat() if assignment.completed_at else None,
                }
            )

        return {
            "highlights": highlights,
            "recent_activity": recent_activity,
        }
