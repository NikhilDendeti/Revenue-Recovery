from django.db.models import Sum

from .models import Action, Transaction


def compute_summary() -> dict:
    total_count = Transaction.objects.count()
    at_risk_total = Transaction.objects.aggregate(s=Sum("amount"))["s"] or 0
    recovered_total = (
        Action.objects.filter(result=Action.Result.SUCCESS).aggregate(s=Sum("amount_recovered"))["s"] or 0
    )
    recovered_count = Transaction.objects.filter(status=Transaction.Status.RECOVERED).count()
    escalated_count = Transaction.objects.filter(status=Transaction.Status.ESCALATED).count()
    held_count = Transaction.objects.filter(status=Transaction.Status.HELD).count()
    failed_count = Transaction.objects.filter(status=Transaction.Status.FAILED).count()
    processed_count = Transaction.objects.exclude(
        status__in=[Transaction.Status.OPEN, Transaction.Status.PROCESSING]
    ).count()
    recovery_rate = (recovered_count / processed_count * 100) if processed_count else 0.0

    return {
        "total_count": total_count,
        "at_risk_total": float(at_risk_total),
        "recovered_total": float(recovered_total),
        "recovered_count": recovered_count,
        "escalated_count": escalated_count,
        "held_count": held_count,
        "failed_count": failed_count,
        "processed_count": processed_count,
        "recovery_rate": round(recovery_rate, 1),
    }
