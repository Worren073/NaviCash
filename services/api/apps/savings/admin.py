"""admin — Registro de metas de ahorro en el panel de administración."""

from django.contrib import admin

from apps.savings.models import GoalContribution, SavingsGoal


class GoalContributionInline(admin.TabularInline):
    """Aportes embebidos en la meta (solo lectura)."""

    model = GoalContribution
    extra = 0
    readonly_fields = ("amount", "currency", "amount_goal_currency", "created_at")
    can_delete = False


@admin.register(SavingsGoal)
class SavingsGoalAdmin(admin.ModelAdmin):
    """Admin: metas de ahorro con sus aportes."""

    list_display = ("name", "currency", "target_amount", "total_contributed", "user")
    search_fields = ("name", "user__email")
    inlines = [GoalContributionInline]


@admin.register(GoalContribution)
class GoalContributionAdmin(admin.ModelAdmin):
    """Admin: aportes individuales."""

    list_display = ("goal", "amount", "currency", "amount_goal_currency", "created_at", "user")
    list_filter = ("currency",)
    search_fields = ("goal__name", "note", "user__email")
    readonly_fields = ("amount_goal_currency", "created_at")