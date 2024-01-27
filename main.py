from discord import Activity, Intents, ActivityType
from discord.ext import commands
from loademon.secret import API_KEY


class Invited(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="??",
            intents=Intents.all(),
            activity=Activity(type=ActivityType.competing, name="Davet Et Kazan!"),
            help_command=None,
        )

    async def on_ready(self):
        print(f"{__class__.__name__} is ready!")

    async def on_command_error(
        self, context: commands.Context, e: Exception, /
    ) -> None:
        if e.__class__ == commands.CommandNotFound:
            await context.send(
                f"**{context.message.content.split()[0]}** komutu bulunamadı.",
                delete_after=5,
            )

        if e.__class__ == commands.NotOwner:
            await context.send(content="Yetkisiz kullanım!", delete_after=1)

    async def setup_hook(self) -> None:
        await self.load_extension("cogs.invite")


Invited().run(API_KEY)
