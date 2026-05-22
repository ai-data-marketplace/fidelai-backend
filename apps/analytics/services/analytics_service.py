from datetime import timedelta

from django.db.models import Avg, Count, DecimalField, IntegerField, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from apps.documents.models import RawDocument, ReviewStatusChoices
from apps.processing.models import Annotation, ExpertReview, ExpertTaskAssignment, TaskAssignment, TaskAssignmentStatusChoices
from apps.scoring.models import ScoreLog, ScoreActionTypeChoices, UserScore


class AnalyticsService:
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
            return 100.0 if current else 0.0
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

        weekly_performance = [
            {
                "period": str(row["period"]),
                "tasks_completed": int(row["tasks_completed"]),
                "points_earned": points_by_day.get(str(row["period"]), 0),
            }
            for row in weekly_rows
        ]

        confidence_distribution = [
            {"label": row["confidence"], "value": int(row["value"])}
            for row in (
                Annotation.objects.filter(annotator=self.user)
                .values("confidence")
                .annotate(value=Count("id"))
                .order_by("confidence")
            )
        ]

        readability_distribution = [
            {"label": row["readability"], "value": int(row["value"])}
            for row in (
                Annotation.objects.filter(annotator=self.user)
                .values("readability")
                .annotate(value=Count("id"))
                .order_by("readability")
            )
        ]

        avg_time_trend = [
            {
                "period": str(row["period"]),
                "avg_time_minutes": round((row["avg_time_seconds"] or 0.0) / 60.0, 2),
            }
            for row in (
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
        ]

        for card in cards:
            delta = card.get("delta")
            if delta and card["key"] in ("overall_performance", "points_earned"):
                delta["label"] = f"{self._format_signed(delta['value'])} {delta['label']}"
            elif delta and card["key"] == "tasks_completed":
                sign = "+" if delta["value"] >= 0 else ""
                delta["label"] = f"{sign}{int(delta['value'])} {delta['label']}"

        return {
            "cards": cards,
            "graphs": {
                "weekly_performance": weekly_performance,
                "confidence_distribution": confidence_distribution,
                "readability_distribution": readability_distribution,
                "avg_time_trend": avg_time_trend,
            },
            "meta": {"lifetime_points": lifetime_points},
        }

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
            {"key": "tasks_completed", "label": "Tasks Completed", "value": completed_tasks, "display_value": str(completed_tasks)},
            {"key": "accuracy", "label": "Accuracy", "value": current_accuracy, "display_value": f"{current_accuracy}%"},
            {"key": "current_streak", "label": "Current Streak", "value": current_streak, "display_value": f"{current_streak} days"},
            {"key": "total_points", "label": "Total Points", "value": total_points, "display_value": f"{total_points:,}"},
            {"key": "assigned_tasks", "label": "Assigned Tasks", "value": assigned_tasks, "display_value": str(assigned_tasks)},
        ]

        recent_activity = [
            {
                "id": str(assignment.id),
                "task_name": assignment.task.name,
                "status": assignment.status,
                "assigned_at": assignment.assigned_at.isoformat(),
                "completed_at": assignment.completed_at.isoformat() if assignment.completed_at else None,
            }
            for assignment in TaskAssignment.objects.filter(annotator=self.user).select_related("task").order_by("-assigned_at")[:5]
        ]

        return {"highlights": highlights, "recent_activity": recent_activity}

    def get_contributor_dashboard(self):
        user_score, _ = UserScore.objects.get_or_create(user=self.user)
        submissions_qs = RawDocument.objects.filter(user=self.user)

        total_submissions = submissions_qs.count()
        pending_review = submissions_qs.filter(review_status=ReviewStatusChoices.PENDING_REVIEW).count()
        approved = submissions_qs.filter(review_status=ReviewStatusChoices.APPROVED).count()

        submissions_over_time_qs = (
            submissions_qs.filter(created_at__gte=self.now - timedelta(days=29))
            .annotate(period=TruncDate("created_at"))
            .values("period")
            .annotate(
                total_submissions=Count("id"),
                pending_review=Count("id", filter=Q(review_status=ReviewStatusChoices.PENDING_REVIEW)),
                approved=Count("id", filter=Q(review_status=ReviewStatusChoices.APPROVED)),
                rejected=Count("id", filter=Q(review_status=ReviewStatusChoices.REJECTED)),
            )
            .order_by("period")
        )

        return {
            "cards": [
                {"key": "total_submissions", "label": "Total Submissions", "value": total_submissions, "display_value": str(total_submissions)},
                {"key": "pending_review", "label": "Pending Review", "value": pending_review, "display_value": f"{pending_review:02d}"},
                {"key": "approved", "label": "Approved", "value": approved, "display_value": str(approved)},
                {"key": "total_score", "label": "Total Score", "value": int(user_score.total_points), "display_value": f"{int(user_score.total_points):,}"},
            ],
            "graphs": {
                "submissions_over_time": [
                    {
                        "period": str(row["period"]),
                        "total_submissions": int(row["total_submissions"]),
                        "pending_review": int(row["pending_review"]),
                        "approved": int(row["approved"]),
                        "rejected": int(row["rejected"]),
                    }
                    for row in submissions_over_time_qs
                ]
            },
        }

    def get_expert_overview(self):
        assignments_qs = ExpertTaskAssignment.objects.filter(expert=self.user)
        reviews_qs = ExpertReview.objects.filter(expert=self.user)

        total_assigned_tasks = assignments_qs.count()
        active_tasks = assignments_qs.filter(
            status__in=(
                TaskAssignmentStatusChoices.ASSIGNED,
                TaskAssignmentStatusChoices.ACCEPTED,
                TaskAssignmentStatusChoices.IN_PROGRESS,
            )
        ).count()
        submitted_tasks = assignments_qs.filter(status=TaskAssignmentStatusChoices.SUBMITTED).count()
        total_reviews = reviews_qs.count()

        completion_durations = [
            (completed_at - assigned_at).total_seconds()
            for assigned_at, completed_at in assignments_qs.filter(completed_at__isnull=False).values_list("assigned_at", "completed_at")
            if assigned_at and completed_at
        ]
        avg_completion_seconds = round(sum(completion_durations) / len(completion_durations), 1) if completion_durations else 0.0

        review_trend_qs = (
            reviews_qs.filter(created_at__gte=self.now - timedelta(days=29))
            .annotate(period=TruncDate("created_at"))
            .values("period")
            .annotate(total_reviews=Count("id"))
            .order_by("period")
        )

        return {
            "cards": [
                {"key": "assigned_tasks", "label": "Assigned Tasks", "value": total_assigned_tasks, "display_value": str(total_assigned_tasks)},
                {"key": "active_tasks", "label": "Active Tasks", "value": active_tasks, "display_value": str(active_tasks)},
                {"key": "submitted_tasks", "label": "Submitted Tasks", "value": submitted_tasks, "display_value": str(submitted_tasks)},
                {"key": "reviews_submitted", "label": "Reviews Submitted", "value": total_reviews, "display_value": str(total_reviews)},
                {
                    "key": "avg_completion_time",
                    "label": "Avg. Completion Time",
                    "value": round(avg_completion_seconds / 60.0, 1),
                    "display_value": self._format_duration(avg_completion_seconds),
                },
            ],
            "graphs": {
                "review_trend": [
                    {"period": str(row["period"]), "total_reviews": int(row["total_reviews"])}
                    for row in review_trend_qs
                ]
            },
        }

    def get_expert_dashboard(self):
        assignments_qs = ExpertTaskAssignment.objects.filter(expert=self.user)
        reviews_qs = ExpertReview.objects.filter(expert=self.user)

        total_assigned_tasks = assignments_qs.count()
        active_tasks = assignments_qs.filter(
            status__in=(
                TaskAssignmentStatusChoices.ASSIGNED,
                TaskAssignmentStatusChoices.ACCEPTED,
                TaskAssignmentStatusChoices.IN_PROGRESS,
            )
        ).count()
        submitted_tasks = assignments_qs.filter(status=TaskAssignmentStatusChoices.SUBMITTED).count()
        total_reviews = reviews_qs.count()
        recent_assignments = assignments_qs.select_related("expert_task").order_by("-assigned_at")[:5]

        return {
            "highlights": [
                {"key": "assigned_tasks", "label": "Assigned Tasks", "value": total_assigned_tasks, "display_value": str(total_assigned_tasks)},
                {"key": "active_tasks", "label": "Active Tasks", "value": active_tasks, "display_value": str(active_tasks)},
                {"key": "submitted_tasks", "label": "Submitted Tasks", "value": submitted_tasks, "display_value": str(submitted_tasks)},
                {"key": "reviews_submitted", "label": "Reviews Submitted", "value": total_reviews, "display_value": str(total_reviews)},
            ],
            "recent_activity": [
                {
                    "id": str(assignment.id),
                    "task_name": assignment.expert_task.name,
                    "status": assignment.status,
                    "assigned_at": assignment.assigned_at.isoformat(),
                    "completed_at": assignment.completed_at.isoformat() if assignment.completed_at else None,
                }
                for assignment in recent_assignments
            ],
        }

    def get_admin_dashboard(self):
        from apps.datasets.models import Dataset, DatasetStatusChoices
        from apps.marketplace.models import Order, PaymentStatusChoices
        from apps.payments.models import WithdrawalRequest, WithdrawalStatusChoices
        from apps.users.models import CustomUser, RoleApplication, RoleApplicationStatusChoices, RoleChoices

        def format_etb_k(amount):
            amount = float(amount or 0)
            if amount >= 1000:
                return f"ETB {amount / 1000:.1f}k"
            return f"ETB {amount:.1f}"

        previous_month_snapshot_end = self.current_month_start - timedelta(seconds=1)

        total_users = CustomUser.objects.count()
        previous_total_users = CustomUser.objects.filter(created_at__lte=previous_month_snapshot_end).count()

        active_contributors = CustomUser.objects.filter(role=RoleChoices.CONTRIBUTOR, is_active=True).count()
        previous_active_contributors = CustomUser.objects.filter(
            role=RoleChoices.CONTRIBUTOR,
            is_active=True,
            created_at__lte=previous_month_snapshot_end,
        ).count()

        pending_approvals = RoleApplication.objects.filter(status=RoleApplicationStatusChoices.PENDING).count()
        previous_pending_approvals = RoleApplication.objects.filter(
            status=RoleApplicationStatusChoices.PENDING,
            submitted_at__lte=previous_month_snapshot_end,
        ).count()

        total_datasets = Dataset.objects.count()
        previous_total_datasets = Dataset.objects.filter(created_at__lte=previous_month_snapshot_end).count()

        total_revenue = Order.objects.filter(payment_status=PaymentStatusChoices.PAID).aggregate(
            amount=Coalesce(Sum("total_amount"), Value(0), output_field=DecimalField(max_digits=14, decimal_places=2))
        )["amount"]
        current_month_revenue = Order.objects.filter(
            payment_status=PaymentStatusChoices.PAID,
            created_at__gte=self.current_month_start,
        ).aggregate(amount=Coalesce(Sum("total_amount"), Value(0), output_field=DecimalField(max_digits=14, decimal_places=2)))["amount"]
        previous_month_revenue = Order.objects.filter(
            payment_status=PaymentStatusChoices.PAID,
            created_at__gte=self.previous_month_start,
            created_at__lte=self.previous_month_end,
        ).aggregate(amount=Coalesce(Sum("total_amount"), Value(0), output_field=DecimalField(max_digits=14, decimal_places=2)))["amount"]

        total_processing_documents = RawDocument.objects.count()
        previous_total_processing_documents = RawDocument.objects.filter(created_at__lte=previous_month_snapshot_end).count()

        role_app_activity = [
            {
                "id": f"role-application-{row['id']}",
                "activity_type": "role_application_review",
                "title": f"Reviewed {row['role_applied_for']} application",
                "status": row["status"],
                "timestamp": row["reviewed_at"],
            }
            for row in RoleApplication.objects.filter(reviewed_by=self.user, reviewed_at__isnull=False)
            .values("id", "role_applied_for", "status", "reviewed_at")
            .order_by("-reviewed_at")[:5]
        ]

        payout_activity = [
            {
                "id": f"withdrawal-{row['id']}",
                "activity_type": "withdrawal_review",
                "title": "Reviewed withdrawal request",
                "status": row["status"],
                "timestamp": row["processed_at"],
            }
            for row in WithdrawalRequest.objects.filter(reviewed_by=self.user, processed_at__isnull=False)
            .values("id", "status", "processed_at")
            .order_by("-processed_at")[:5]
        ]

        dataset_activity = [
            {
                "id": f"dataset-{row['id']}",
                "activity_type": "dataset_approval",
                "title": f"Approved dataset: {row['title']}",
                "status": DatasetStatusChoices.APPROVED,
                "timestamp": row["approved_at"],
            }
            for row in Dataset.objects.filter(approved_by=self.user, approved_at__isnull=False)
            .values("id", "title", "approved_at")
            .order_by("-approved_at")[:5]
        ]

        combined_activity = role_app_activity + payout_activity + dataset_activity
        combined_activity.sort(key=lambda item: item["timestamp"], reverse=True)

        recent_activity = [
            {
                "id": item["id"],
                "activity_type": item["activity_type"],
                "title": item["title"],
                "status": item["status"],
                "timestamp": item["timestamp"].isoformat() if item["timestamp"] else None,
            }
            for item in combined_activity[:10]
        ]

        cards = [
            {
                "key": "total_users",
                "label": "Total Users",
                "value": total_users,
                "display_value": f"{total_users:,}",
                "delta": {
                    "value": self._pct_change(total_users, previous_total_users),
                    "label": "from last month",
                },
            },
            {
                "key": "active_contributors",
                "label": "Active Contributors",
                "value": active_contributors,
                "display_value": f"{active_contributors:,}",
                "delta": {
                    "value": self._pct_change(active_contributors, previous_active_contributors),
                    "label": "from last month",
                },
            },
            {
                "key": "pending_approvals",
                "label": "Pending Approvals",
                "value": pending_approvals,
                "display_value": f"{pending_approvals:,}",
                "delta": {
                    "value": self._pct_change(pending_approvals, previous_pending_approvals),
                    "label": "from last month",
                },
            },
            {
                "key": "total_datasets",
                "label": "Total Datasets",
                "value": total_datasets,
                "display_value": f"{total_datasets:,}",
                "delta": {
                    "value": self._pct_change(total_datasets, previous_total_datasets),
                    "label": "from last month",
                },
            },
            {
                "key": "total_revenue",
                "label": "Total Revenue",
                "value": float(total_revenue or 0),
                "display_value": format_etb_k(total_revenue),
                "delta": {
                    "value": self._pct_change(float(current_month_revenue or 0), float(previous_month_revenue or 0)),
                    "label": "from last month",
                },
            },
            {
                "key": "total_processing_documents",
                "label": "Uploaded Documents",
                "value": total_processing_documents,
                "display_value": f"{total_processing_documents:,}",
                "delta": {
                    "value": self._pct_change(total_processing_documents, previous_total_processing_documents),
                    "label": "from last month",
                },
            },
        ]

        for card in cards:
            delta = card.get("delta")
            if delta:
                delta["label"] = f"{self._format_signed(delta['value'])} {delta['label']}"

        return {"cards": cards, "recent_activity": recent_activity}
