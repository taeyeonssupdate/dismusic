import asyncio
import os

import async_timeout
import discord
from discord.ext import commands
from wavelink import Player

from .errors import InvalidLoopMode, NotEnoughSong, NothingIsPlaying


class MusicControllerView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        self.clear_items()
        self.stop()

    async def get_player(interaction):
        try:
            player: DisPlayer = interaction.message.guild.getattr("voice_client", None)
            if not player: raise AttributeError("no voice_client")
        except Exception as e:
            await interaction.message.channel.send(f"get player error: {e}")
        return player

    @discord.ui.button(
        label="跳過",
        style=discord.ButtonStyle.grey,
        emoji="⏭️",
        custom_id="skip",
    )
    async def grey(self, button: discord.ui.Button, interaction: discord.Interaction):
        player: DisPlayer = self.get_player(interaction)

        if player.loop == "當前歌曲":
            player.loop = "無"

        await player.stop()

        player.client.dispatch("dismusic_track_skip", player)
        for child in self.children:
            child.disabled = True
        button.label = "已跳過"
        await interaction.response.edit_message(view=self)

    @discord.ui.button(
        label="暫停",
        style=discord.ButtonStyle.grey,
        emoji="⏯️",
        custom_id="pause_resume"
    )
    async def green(self, button: discord.ui.Button, interaction: discord.Interaction):
        player: DisPlayer = self.get_player(interaction)

        if not player.is_playing():
            button.disabled = True
            button.label = "沒有在播放任何音源"
        elif player.is_paused():
            button.label = "暫停"
            await player.set_pause(pause=False)
            player.client.dispatch("dismusic_player_resume", player)
        else:
            button.label = "播放"
            await player.set_pause(pause=True)
            player.client.dispatch("dismusic_player_pause", player)

        return await interaction.response.edit_message(view=self)

    @discord.ui.button(
        label="停止播放",
        style=discord.ButtonStyle.grey,
        emoji="⏹️",
        custom_id="stop"
    )
    async def red(self, button: discord.ui.Button, interaction: discord.Interaction):
        player: DisPlayer = self.get_player(interaction)

        await player.destroy()
        for child in self.children:
            child.disabled = True
        button.label = "已停止播放"
        await interaction.response.edit_message(view=self)
        player.client.dispatch("dismusic_player_stop", player)


class DisPlayer(Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.queue = asyncio.Queue()
        self.loop = "無"  # 當前歌曲, 播放列表
        self.bound_channel = None
        self.track_provider = "yt"

    async def destroy(self) -> None:
        self.queue = None

        await super().stop()
        await super().disconnect()

    async def do_next(self) -> None:
        if self.is_playing():
            return

        timeout = int(os.getenv("DISMUSIC_TIMEOUT", 300))

        try:
            with async_timeout.timeout(timeout):
                track = await self.queue.get()
        except asyncio.TimeoutError:
            if not self.is_playing():
                await self.destroy()

            return

        self._source = track
        await self.play(track)
        self.client.dispatch("dismusic_track_start", self, track)
        await self.invoke_player()

    async def set_loop(self, loop_type: str) -> None:
        valid_types = ["無", "當前歌曲", "播放列表"]

        if not self.is_playing():
            raise NothingIsPlaying("沒有播放中個音源 無法循環")

        if not loop_type:
            if valid_types.index(self.loop) >= 2:
                loop_type = "無"
            else:
                loop_type = valid_types[valid_types.index(self.loop) + 1]

            if loop_type == "播放列表" and len(self.queue._queue) < 1:
                loop_type = "無"

        if loop_type.upper() == "播放列表" and len(self.queue._queue) < 1:
            raise NotEnoughSong("播放列表必須有兩首以上的音源")

        if loop_type.upper() not in valid_types:
            raise InvalidLoopMode("循環模式必須為 `無`, `當前歌曲` 或 `播放列表`")

        self.loop = loop_type.upper()

        return self.loop

    async def invoke_player(self, ctx: commands.Context = None) -> None:
        track = self.source

        if not track:
            raise NothingIsPlaying("沒有播放中的音源")

        embed = discord.Embed(title=track.title, url=track.uri, color=discord.Color(0x2F3136))
        embed.set_author(
            name=track.author,
            url=track.uri,
            icon_url=self.client.user.display_avatar.url,
        )
        try:
            embed.set_thumbnail(url=track.thumb)
        except AttributeError:
            embed.set_thumbnail(
                url="https://cdn.discordapp.com/attachments/776345413132877854/940540758442795028/unknown.png"
            )
        embed.add_field(
            name="長度",
            value=f"{int(track.length // 60)}:{int(track.length % 60)}",
        )
        embed.add_field(name="循環", value=self.loop)
        embed.add_field(name="音量", value=self.volume)

        next_song = ""

        if self.loop == "當前歌曲":
            next_song = self.source.title
        else:
            if len(self.queue._queue) > 0:
                next_song = self.queue._queue[0].title

        if next_song:
            embed.add_field(name="下一首", value=next_song, inline=False)

        if not ctx:
            return await self.bound_channel.send(embed=embed, view=MusicControllerView())

        await ctx.send(embed=embed, view=MusicControllerView())
