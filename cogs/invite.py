import discord
import redis.asyncio as redis
from datetime import datetime, timezone
from discord.ext import commands, tasks


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

        now = datetime.now(timezone.utc)

        if (now - interaction.user.created_at).days < 30:
            await self.r.hset(f"info:{user_id}", "checked", "True")
            return await interaction.followup.send(
                "Spam kontrolü tamamlandı. Ancak davet olarak sayılmadı. (Hesap yaşı 1 aydan az.)",
                ephemeral=True,
            )

        # if interaction.user.flags.did_rejoin:
        #     await self.r.hset(f"info:{user_id}", "checked", "True")
        #     return await interaction.followup.send(
        #         "Spam kontrolü tamamlandı. Ancak davet olarak sayılmadı. (Kullanıcı sunucudan çıkıp tekrar katıldı.)",
        #         ephemeral=True,
        #     )

        if not await self.r.exists(f"info:{user_id}"):
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
            return await interaction.followup.send(
                "Spam kontrolü başlatılamadı. (Kişi başka birinin daveti ile katılmamış.)",
                ephemeral=True,
            )

        if inviter_id == interaction.user.id:
            return await interaction.followup.send(
                "Spam kontrolü başlatılamadı. (Kişi kendi daveti ile katılmış. Çakkaaaal :D)",
                ephemeral=True,
            )

        inviter = await self.bot.fetch_user(inviter_id)
        if inviter is None:
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
        self.invite_channel_id = 1185641908400300132
        self.invite_channel: discord.TextChannel = None
        self.invite_log_message = None
        self.update_invites.start()

    async def cog_load(self) -> None:
        self.bot.add_view(SpamButton(self.bot))
        guild_id = 951884318198874192
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
        return None

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        invites_before_join = self.invites[member.guild.id]
        invites_after_join = await member.guild.invites()

        for invite in invites_after_join:
            print(invite.code, invite.uses)

        # if member.flags.did_rejoin:
        #     return

        if member.bot:
            return

        for invite in invites_before_join:
            finded_invite = self.find_invite_by_code(invites_after_join, invite.code)
            if finded_invite is None:
                continue

            if invite.uses < finded_invite.uses:
                print(f"{invite.inviter} invited {member} to {member.guild}")
                # await self.r.zadd("Ivites", {invite.inviter.id: 1}, incr=True)
                # deleted this ^ version beacuse we are not want to count invites before joined user is write a message
                await self.r.hset(f"info:{member.id}", "inviter", invite.inviter.id)
                # saved inviter id to redis. If joined user is write a message and click te button we are count this user's invites
                # or joined user leave the guild we are not count this user's invites.
                # if user leave the guild we will also delete if we have already counted the user's invites.

        self.invites[member.guild.id] = invites_after_join

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        print(f"{invite.inviter} created invite {invite} in {invite.guild}")
        await self.r.hset(f"invite:{invite.code}", "inviter", invite.inviter.id)
        await self.r.hset(f"invite:{invite.code}", "uses", invite.uses)
        self.invites[invite.guild.id] = await invite.guild.invites()
        for invite_x in self.invites[invite.guild.id]:
            if invite_x.code == invite.code:
                print("Invite:", invite_x.code, invite_x.uses)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        member_inviter = await self.r.hget(f"info:{member.id}", "inviter")
        if member_inviter is None:
            return
        member_inviter = member_inviter.decode("utf-8")

        if member_inviter is None:
            return

        invite_count = await self.r.zscore("Ivites", member_inviter)
        if invite_count is None:
            return
        try:
            invite_count = invite_count.decode("utf-8")
        except:
            pass

        invite_count = int(invite_count)

        if invite_count <= 0:
            return

        await self.r.zadd("Ivites", {member_inviter: -1}, incr=True)

        invite_channel = await self.bot.fetch_channel(self.invite_channel_id)
        # get Ivites sorted set from redis
        invites = await self.r.zrevrange("Ivites", 0, -1, withscores=True)
        invites = dict(invites)
        # embed for invite scores
        embed = discord.Embed(title="Davet Skorları", color=discord.Color.blurple())
        for invite_id, invite_count in invites.items():
            invite = await self.bot.fetch_user(int(invite_id.decode("utf-8")))
            embed.add_field(name=invite.name, value=int(invite_count), inline=False)
        await invite_channel.purge(limit=100)
        await invite_channel.send(embed=embed)

    @tasks.loop(seconds=30)
    async def update_invites(self):
        invite_channel = await self.bot.fetch_channel(self.invite_channel_id)
        # get Ivites sorted set from redis
        invites = await self.r.zrevrange("Ivites", 0, -1, withscores=True)
        invites = dict(invites)
        print("Listeyi güncelliyorum")
        # embed for invite scores
        embed = discord.Embed(title="Davet Skorları", color=discord.Color.blurple())
        for invite_id, invite_count in invites.items():
            if int(invite_count) == 0:
                continue
            invite = await self.bot.fetch_user(int(invite_id.decode("utf-8")))
            embed.add_field(name=invite.name, value=int(invite_count), inline=False)
        await invite_channel.purge(limit=100)
        await invite_channel.send(embed=embed)

    @update_invites.before_loop
    async def before_update_invites(self):
        await self.bot.wait_until_ready()

    @commands.has_any_role(1185604201242431608, 1185605115302924440)  # Kurucu, Yönetici
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
            1185996673223233648,
            1196357456494870628,
        ]:  # tr genel, en genel
            return

        if await self.r.exists(f"info:{message.author.id}"):
            await self.r.hincrby(f"info:{message.author.id}", "messages", 1)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Invite(bot))
