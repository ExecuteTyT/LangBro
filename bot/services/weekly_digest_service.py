import logging
from datetime import date, datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Challenge, UserChallenge
from bot.db.repositories.battle_repo import BattleRepository
from bot.db.repositories.challenge_repo import ChallengeRepository
from bot.db.repositories.stats_repo import StatsRepository

logger = logging.getLogger(__name__)


class WeeklyDigestService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def generate_weekly_digest(self, challenge: Challenge) -> str | None:
        today = datetime.now(timezone.utc).date()
        # Current week: Monday to Sunday
        week_end = today
        week_start = today - timedelta(days=6)

        # Previous week for position changes
        prev_week_end = week_start - timedelta(days=1)
        prev_week_start = prev_week_end - timedelta(days=6)

        stats_repo = StatsRepository(self.session)
        challenge_repo = ChallengeRepository(self.session)

        members = await challenge_repo.get_challenge_members(challenge.id)
        if not members:
            return None

        # Current week points
        week_data = await stats_repo.get_week_points(
            challenge.id, week_start, week_end
        )
        week_map = {uc_id: pts for uc_id, pts in week_data}

        # Previous week points for comparison
        prev_data = await stats_repo.get_week_points(
            challenge.id, prev_week_start, prev_week_end
        )
        prev_map = {uc_id: pts for uc_id, pts in prev_data}

        # Build ranking with position changes
        ranking = []
        for m in members:
            await self.session.refresh(m, ["user"])
            name = m.user.display_name or m.user.first_name
            wk_pts = week_map.get(m.id, 0)
            prev_pts = prev_map.get(m.id, 0)
            ranking.append({
                "name": name,
                "week_pts": wk_pts,
                "prev_pts": prev_pts,
                "streak": m.current_streak,
                "total_pts": m.total_points,
            })

        ranking.sort(key=lambda x: x["week_pts"], reverse=True)

        # Assign current and previous ranks
        prev_sorted = sorted(ranking, key=lambda x: x["prev_pts"], reverse=True)
        prev_rank_map = {r["name"]: i + 1 for i, r in enumerate(prev_sorted)}

        # MVP
        mvp = ranking[0] if ranking else None

        # Best streak
        best_streak_member = max(ranking, key=lambda x: x["streak"]) if ranking else None

        # Comeback: biggest rank improvement
        comeback = None
        max_improvement = 0
        for i, r in enumerate(ranking):
            current_rank = i + 1
            prev_rank = prev_rank_map.get(r["name"], current_rank)
            improvement = prev_rank - current_rank
            if improvement > max_improvement and r["week_pts"] > 0:
                max_improvement = improvement
                comeback = r

        # Rocket: biggest absolute point gain vs previous week
        rocket = None
        max_gain = 0
        for r in ranking:
            gain = r["week_pts"] - r["prev_pts"]
            if gain > max_gain:
                max_gain = gain
                rocket = r

        # Format
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines = []
        for i, r in enumerate(ranking, 1):
            if r["week_pts"] == 0:
                continue
            medal = medals.get(i, f"{i}.")
            current_rank = i
            prev_rank = prev_rank_map.get(r["name"], current_rank)
            diff = prev_rank - current_rank
            trend = "↑" if diff > 0 else ("↓" if diff < 0 else "→")
            streak = f" 🔥{r['streak']}" if r["streak"] > 0 else ""
            lines.append(
                f"{medal} <b>{r['name']}</b> — {r['week_pts']} pts {trend}{streak}"
            )

        text = f"📊 <b>Еженедельная сводка — {challenge.title}</b>\n"
        text += f"📅 {week_start.strftime('%d.%m')} — {week_end.strftime('%d.%m')}\n\n"

        if mvp and mvp["week_pts"] > 0:
            text += f"🏆 <b>MVP недели:</b> {mvp['name']} ({mvp['week_pts']} pts)\n\n"

        text += "📈 <b>Рейтинг:</b>\n" + "\n".join(lines) + "\n"

        if best_streak_member and best_streak_member["streak"] > 0:
            text += (
                f"\n🔥 <b>Лучший streak:</b> "
                f"{best_streak_member['name']} — {best_streak_member['streak']} дней\n"
            )

        if comeback and max_improvement > 0:
            text += (
                f"🔄 <b>Камбэк недели:</b> "
                f"{comeback['name']} (+{max_improvement} позиций)\n"
            )

        if rocket and max_gain > 0:
            text += (
                f"🚀 <b>Рокет:</b> "
                f"{rocket['name']} (+{max_gain} pts vs прошлая неделя)\n"
            )

        # Battle results
        battle_repo = BattleRepository(self.session)
        battle = await battle_repo.get_active_battle(challenge.id)
        if not battle:
            # Check completed battles this week
            from sqlalchemy import select
            from bot.db.models import WeeklyBattle
            stmt = select(WeeklyBattle).where(
                WeeklyBattle.challenge_id == challenge.id,
                WeeklyBattle.status == "completed",
                WeeklyBattle.week_start >= week_start,
            )
            result = await self.session.execute(stmt)
            battle = result.scalar_one_or_none()

        if battle:
            pairs = await battle_repo.get_battle_pairs(battle.id)
            if pairs:
                text += "\n⚔️ <b>Батлы:</b>\n"
                for pair in pairs:
                    if pair.winner_id:
                        p1 = await self.session.get(UserChallenge, pair.player1_id)
                        await self.session.refresh(p1, ["user"])
                        p1_name = p1.user.display_name or p1.user.first_name

                        if pair.player2_id:
                            p2 = await self.session.get(UserChallenge, pair.player2_id)
                            await self.session.refresh(p2, ["user"])
                            p2_name = p2.user.display_name or p2.user.first_name
                            winner = p1_name if pair.winner_id == pair.player1_id else p2_name
                            text += (
                                f"  {p1_name} ({pair.player1_points}) vs "
                                f"{p2_name} ({pair.player2_points}) "
                                f"→ 🏆 {winner}\n"
                            )
                        else:
                            text += f"  {p1_name} — bye\n"

        return text
