import discord
import os
import traceback
import asyncio
import time
import GPUtil as gputil

from discord.utils import MISSING
from typing import Optional, Union, Callable
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

load_dotenv()

GUIDE_ID = os.environ.get("GUIDE_ID")
assert GUIDE_ID is not None
MY_GUILD = discord.Object(id=int(GUIDE_ID))  # replace with your guild id


class Client(discord.Client):

    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        # A CommandTree is a special type that holds all the application command
        # state required to make it work. This is a separate class because it
        # allows all the extra state to be opt-in.
        # Whenever you want to work with application commands, your tree is used
        # to store and work with them.
        # Note: When using commands.Bot instead of discord.Client, the bot will
        # maintain its own tree instead.
        self.tree = app_commands.CommandTree(self)

    # In this basic example, we just synchronize the app commands to one guild.
    # Instead of specifying a guild to every command, we copy over our global commands instead.
    # By doing so, we don't have to wait up to an hour until they are shown to the end-user.
    async def setup_hook(self):
        # This copies the global commands over to your guild.
        self.tree.copy_global_to(guild=MY_GUILD)
        await self.tree.sync(guild=MY_GUILD)


intents = discord.Intents.default()
client = Client(intents=intents)


def format_time(seconds):
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60

    if hours > 0:
        return "{:02d}:{:02d}:{:02d}".format(int(hours), int(minutes),
                                             int(seconds))
    else:
        return "{:02d}:{:02d}".format(int(minutes), int(seconds))


class GPU(discord.ui.Modal, title='GPU'):
    minutes: discord.ui.TextInput = discord.ui.TextInput(
        label='minutes',
        style=discord.TextStyle.short,
        placeholder='10',
        required=True,
        max_length=256,
    )

    def __init__(
            self,
            *,
            title: str = ...,  # type: ignore
            timeout: Optional[float] = None,
            custom_id: str = ...,  # type: ignore
    ) -> None:
        super().__init__(title=title, timeout=timeout, custom_id=custom_id)

    def validate(self) -> bool:
        try:
            if self.minutes.value is None:
                return False
            m = int(self.minutes.value)
            return True
        except ValueError:
            return False

    @tasks.loop(seconds=60, count=None, reconnect=False)
    async def running_task(self, interaction: discord.Interaction,
                           start_time: float, edit_fn: Callable):
        try:
            deviceIDs = gputil.getAvailable(
                order='first',
                limit=1,
                maxLoad=0.1,
                maxMemory=0.1,
                includeNan=False,
                excludeID=[],
                excludeUUID=[],
            )
        except Exception as e:
            await edit_fn(
                content=f"**GPU Avaliable**: You don't have CUDA installed")
            self.running_task.cancel()
            return
        if len(deviceIDs) > 0:
            await asyncio.sleep(60 * int(self.minutes.value))
            deviceIDs_again = gputil.getAvailable(
                order='first',
                limit=1,
                maxLoad=0.1,
                maxMemory=0.1,
                includeNan=False,
                excludeID=[],
                excludeUUID=[],
            )
            intersection = list(set(deviceIDs) & set(deviceIDs_again))
            if len(intersection) > 0:
                await edit_fn(
                    content=
                    f"**GPU Avaliable**: It takes {format_time(time.time() - start_time)} to get a GPU ({intersection})! Go use it!"
                )
                self.running_task.cancel()
                return

    @running_task.before_loop
    async def running_task_before_loop(self):
        pass

    @running_task.after_loop
    async def running_task_after_loop(self):
        if self.running_task.is_being_cancelled():
            pass

    async def on_submit(self,
                        interaction: discord.Interaction,
                        use_interaction=False):
        username = interaction.user.name

        valid = self.validate()
        if not valid:
            await interaction.response.send_message(
                content=
                f"**GPU Avaliable**: Please enter a valid number of minutes.",
                ephemeral=True)
            return

        await interaction.followup.send(
            content=
            f"**Request**: submitted by {username} {interaction.user.mention}",
            ephemeral=False)

        edit_fn: Callable = interaction.edit_original_response

        if use_interaction:
            pass
        else:
            interaction_response: discord.interactions.InteractionMessage = await interaction.original_response(
            )
            msg = await interaction_response.reply(
                content=
                f"**GPU Avaliable**: We will notify you when there is a GPU avaliable for at least {self.minutes.value} minutes."
            )
            edit_fn = msg.edit

        self.running_task.start(interaction=interaction,
                                start_time=time.time(),
                                edit_fn=edit_fn)

        # wait for task to finish to retain interaction object
        while (self.running_task.is_running()):
            await asyncio.sleep(1)
        await asyncio.sleep(
            1)  # wait for 1 more second ensure button cancellation is handled
        print(f"Interaction finished: {interaction.id}")

    async def on_error(self, interaction: discord.Interaction,
                       e: Exception) -> None:
        try:
            original_response = await interaction.original_response()
            await interaction.edit_original_response(
                content=f"Internal Error: {e}")
        except discord.NotFound:
            try:
                await interaction.followup.send(content=f"Internal Error: {e}")
            except discord.errors.HTTPException:
                pass
        print(f"Interaction error: {interaction.id}, {e}")
        print(traceback.format_exc())


@client.event
async def on_ready():
    user = client.user
    assert user is not None
    await client.change_presence(activity=discord.Game(name="on the spaceship")
                                 )
    print(f'Logged in as {user} (ID: {user.id})')


@client.tree.command(description="Notify you when there is GPU avaliable")
@app_commands.describe(
    minutes=
    'How many minutes of no utilization and memory is considered available?')
async def gpu(
    interaction: discord.Interaction,
    minutes: str,
):
    await interaction.response.defer()
    imagine = GPU()
    try:
        imagine.minutes._value = minutes
        imagine.minutes._underlying.value = minutes
        await imagine.on_submit(interaction=interaction)
    except Exception as e:
        if imagine.running_task.is_running():
            imagine.running_task.cancel()
        try:
            original_response = await interaction.original_response()
            await interaction.edit_original_response(
                content=f"Internal Error: {e}")
        except discord.NotFound:
            try:
                await interaction.followup.send(content=f"Internal Error: {e}")
            except discord.errors.HTTPException:
                pass
        print(f"Interaction error: {interaction.id}, {e}")
        print(traceback.format_exc())


BOT_TOKEN = os.environ.get("BOT_TOKEN")
assert BOT_TOKEN is not None
client.run(BOT_TOKEN)
