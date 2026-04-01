import logging
import random
from datetime import date, datetime, timezone, timedelta

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import Challenge, UserChallenge
from bot.db.repositories.battle_repo import BattleRepository
from bot.db.repositories.challenge_repo import ChallengeRepository
from bot.db.repositories.stats_repo import StatsRepository
from bot.llm.client import GeminiClient
from bot.llm.prompts.bot_persona import BASE_SYSTEM_PROMPT, PENALTY_TASK_PROMPT

logger = logging.getLogger(__name__)


class BattleService:
    def __init__(self, session: AsyncSession, gemini: GeminiClient):
        self.session = session
        self.repo = BattleRepository(session)
        self.gemini = gemini

    async def create_weekly_battle(
        self, challenge: Challenge, bot: Bot
    ) -> None:
        today = datetime.now(timezone.utc).date()
        # week_start = today (Monday), week_end = Friday
        week_end = today + timedelta(days=4)

        # Check if battle already exists this week
        existing = await self.repo.get_active_battle(challenge.id)
        if existing:
            logger.info("Battle already exists for challenge %s", challenge.id)
            return

        challenge_repo = ChallengeRepository(self.session)
        members = await challenge_repo.get_challenge_members(challenge.id)

        if len(members) < 2:
            logger.info("Not enough members for battle in challenge %s", challenge.id)
            return

        battle = await self.repo.create_battle(challenge.id, today, week_end)

        # Shuffle and pair
        shuffled = list(members)
        random.shuffle(shuffled)

        pairs_text = []
        for i in range(0, len(shuffled), 2):
            p1 = shuffled[i]
            p2 = shuffled[i + 1] if i + 1 < len(shuffled) else None

            await self.repo.create_pair(battle.id, p1.id, p2.id if p2 else None)

            await self.session.refresh(p1, ["user"])
            name1 = p1.user.display_name or p1.user.first_name

            if p2:
                await self.session.refresh(p2, ["user"])
                name2 = p2.user.display_name or p2.user.first_name
                pairs_text.append(f"⚔️ <b>{name1}</b> vs <b>{name2}</b>")
            else:
                pairs_text.append(f"🎫 <b>{name1}</b> — bye (автопроход)")

        text = (
            "⚔️ <b>Weekly Battle начинается!</b>\n\n"
            "Пары на эту неделю:\n"
            + "\n".join(pairs_text)
            + "\n\nНабирайте баллы — итоги в пятницу! 💪"
        )
        await bot.send_message(challenge.chat_id, text)

    async def resolve_weekly_battle(
        self, challenge: Challenge, bot: Bot
    ) -> None:
        battle = await self.repo.get_active_battle(challenge.id)
        if not battle:
            return

        stats_repo = StatsRepository(self.session)
        week_points_list = await stats_repo.get_week_points(
            challenge.id, battle.week_start, battle.week_end
        )
        week_points = {uc_id: pts for uc_id, pts in week_points_list}

        pairs = await self.repo.get_battle_pairs(battle.id)
        results = []

        for pair in pairs:
            p1_pts = week_points.get(pair.player1_id, 0)
            pair.player1_points = p1_pts

            await self.session.refresh(
                await self.session.get(UserChallenge, pair.player1_id), ["user"]
            )
            p1_uc = await self.session.get(UserChallenge, pair.player1_id)
            p1_name = p1_uc.user.display_name or p1_uc.user.first_name

            if pair.player2_id is None:
                # Bye — auto-win
                pair.winner_id = pair.player1_id
                pair.player2_points = 0
                results.append(f"🎫 <b>{p1_name}</b> — bye (автопроход)")
                continue

            p2_pts = week_points.get(pair.player2_id, 0)
            pair.player2_points = p2_pts

            p2_uc = await self.session.get(UserChallenge, pair.player2_id)
            await self.session.refresh(p2_uc, ["user"])
            p2_name = p2_uc.user.display_name or p2_uc.user.first_name

            if p1_pts >= p2_pts:
                winner_id, winner_name = pair.player1_id, p1_name
                loser_id, loser_name, loser_pts = pair.player2_id, p2_name, p2_pts
                winner_pts = p1_pts
            else:
                winner_id, winner_name = pair.player2_id, p2_name
                loser_id, loser_name, loser_pts = pair.player1_id, p1_name, p1_pts
                winner_pts = p2_pts

            pair.winner_id = winner_id

            # Generate penalty task for loser
            loser_uc = await self.session.get(UserChallenge, loser_id)
            await self.session.refresh(loser_uc, ["user"])
            loser_level = loser_uc.user.english_level

            try:
                penalty = await self.gemini.call(
                    prompt=PENALTY_TASK_PROMPT.format(
                        loser_name=loser_name,
                        loser_points=loser_pts,
                        winner_points=winner_pts,
                        winner_name=winner_name,
                        english_level=loser_level,
                    ),
                    system=BASE_SYSTEM_PROMPT,
                    feature="battle_penalty",
                    temperature=0.8,
                    max_tokens=200,
                )
                pair.loser_penalty_task = penalty
            except Exception as e:
                logger.warning("Failed to generate penalty task: %s", e)
                penalty = "Запиши голосовое на 30 секунд на английском о своём дне!"
                pair.loser_penalty_task = penalty

            results.append(
                f"⚔️ <b>{winner_name}</b> ({winner_pts} pts) 🏆 vs "
                f"{loser_name} ({loser_pts} pts)\n"
                f"   📋 Штраф: <i>{penalty}</i>"
            )

        await self.session.flush()
        await self.repo.close_battle(battle.id)

        text = (
            "⚔️ <b>Weekly Battle — Результаты!</b>\n\n"
            + "\n\n".join(results)
        )
        await bot.send_message(challenge.chat_id, text)
