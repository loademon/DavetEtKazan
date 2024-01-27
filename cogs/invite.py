import discord
import redis.asyncio as redis
from discord.ext import commands
from pprint import pprint


class SpamButton(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.r = redis.Redis(host="localhost", port=6379, db=2)
        self.bot = bot

    @discord.ui.button(
        label="Spam Kontrol",
        style=discord.ButtonStyle.green,
        emoji="📝",
        custom_id="spam:control",
    )
    async def spam_control(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        user_id = interaction.user.id

        await interaction.response.send_message(
            "Spam kontrolü başlatıldı.", ephemeral=True
        )

        if await self.r.hget(f"info:{user_id}", "checked") == b"True":
            return await interaction.followup.send(
                "Spam kontrolü zaten tamamlanmış. Hoşgeldiniz.",
                ephemeral=True,
            )

        if not await self.r.exists(f"info:{user_id}"):
            await self.r.hset(f"info:{user_id}", "checked", "True")
            return await interaction.followup.send(
                "Spam kontrolü tamamlanamadı. (Kişi başka birinin daveti ile katılmamış.)",
                ephemeral=True,
            )

        message_count = await self.r.hget(f"info:{user_id}", "messages")
        if message_count is None:
            message_count = b"0"
        message_count = message_count.decode("utf-8")

        if message_count is None or int(message_count) < 3:
            return await interaction.followup.send(
                f"Lütfen bunu yapmadan önce en az 3 mesaj gönderin. Şu anki mesaj sayınız: {message_count}",
                ephemeral=True,
            )

        inviter_id = await self.r.hget(f"info:{user_id}", "inviter")
        inviter_id = inviter_id.decode("utf-8")

        if inviter_id is None:
            await self.r.hset(f"info:{user_id}", "checked", "True")
            return await interaction.followup.send(
                "Spam kontrolü başlatılamadı. (Kişi başka birinin daveti ile katılmamış.)",
                ephemeral=True,
            )

        if inviter_id == interaction.user.id:
            await self.r.hset(f"info:{user_id}", "checked", "True")
            return await interaction.followup.send(
                "Spam kontrolü başlatılamadı. (Kişi kendi daveti ile katılmış. Çakkaaaal :D)",
                ephemeral=True,
            )

        inviter = await self.bot.fetch_user(inviter_id)
        if inviter is None:
            await self.r.hset(f"info:{user_id}", "checked", "True")
            return await interaction.followup.send(
                "Spam kontrolü başlatılamadı. (Sunucuya davet aracılığıyla katılmış ancak davet eden kişi şu an sunucuda değil.)",
                ephemeral=True,
            )

        await self.r.zadd("Ivites", {inviter_id: 1}, incr=True)
        await self.r.hset(f"info:{user_id}", "checked", "True")
        await interaction.followup.send(
            f"Spam kontrolü başarılı. Sunucumuza hoşgeldiniz. Davet eden kişiye ({inviter.name}) 1 davet eklendi.",
            ephemeral=True,
        )


class Invite(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.r = redis.Redis(host="localhost", port=6379, db=2)
        self.invites = {}
        self.invite_channel_id = 1197597072967356536
        self.invite_channel: discord.TextChannel = None
        self.invite_log_message = None

    async def cog_load(self) -> None:
        self.bot.add_view(SpamButton(self.bot))
        guild_id = 1197256636679598193
        guild = await self.bot.fetch_guild(guild_id)
        print(f"listening {guild.name}")

        self.invites[guild_id] = await guild.invites()

        self.invite_channel = await self.bot.fetch_channel(self.invite_channel_id)
        print(f"{self.__class__.__name__} is ready!")

    @staticmethod
    def find_invite_by_code(invites, code):
        for invite in invites:
            if invite.code == code:
                return invite

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        invites_before_join = self.invites[member.guild.id]
        invites_after_join = await member.guild.invites()

        # if member.flags.did_rejoin:
        #     return

        if member.bot:
            return

        for invite in invites_before_join:
            if (
                invite.uses
                < self.find_invite_by_code(invites_after_join, invite.code).uses
            ):
                print(f"{invite.inviter} invited {member} to {member.guild}")
                # await self.r.zadd("Ivites", {invite.inviter.id: 1}, incr=True)
                # deleted this ^ version beacuse we are not want to count invites before joined user is write a message
                await self.r.hset(f"info:{member.id}", "inviter", invite.inviter.id)
                # saved inviter id to redis. If joined user is write a message and click te button we are count this user's invites
                # or joined user leave the guild we are not count this user's invites.
                # if user leave the guild we will also delete if we have already counted the user's invites.

        self.invites[member.guild.id] = invites_after_join

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        member_inviter = await self.r.hget(f"info:{member.id}", "inviter")
        if member_inviter is None:
            return
        member_inviter = member_inviter.decode("utf-8")

        if member_inviter is None:
            return

        invite_count = await self.r.zscore("Ivites", member_inviter)
        invite_count = int(invite_count)

        if invite_count <= 0:
            return

        await self.r.zadd("Ivites", {member_inviter: -1}, incr=True)

        # TODO: edit invite log message

    @commands.has_any_role(1197596893832818809, 1197596898891149353)  # Kurucu, Yönetici
    @commands.command(name="davet-kontrol")
    async def spam_checker(self, ctx: commands.Context):
        content = "Lütfen aşağıdaki butona tıklayarak spam kontrolünü tamamlayınız."
        embed = discord.Embed(title="Spam Kontrol", description=content)
        await ctx.send(embed=embed, view=SpamButton(self.bot))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # if message.author.flags.did_rejoin:  # rejoin not allowed lol :D
        #     return

        if message.author.bot:  # fuck bots
            return

        if message.channel.id not in [
            1197597141502267473,
            1197597146984231004,
        ]:  # tr genel, en genel
            return

        if await self.r.exists(f"info:{message.author.id}"):
            await self.r.hincrby(f"info:{message.author.id}", "messages", 1)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Invite(bot))
