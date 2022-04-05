import asyncio
import os

import async_timeout
import discord
from discord.ext import commands
from wavelink import Player

from .errors import InvalidLoopMode, NotEnoughSong, NothingIsPlaying


class MusicControllerView(discord.ui.View):
    def __init__(self, player):
        super().__init__(timeout=None)
        self.player = player

    @discord.ui.button(
        label="跳過 ⏭️",
        style=discord.ButtonStyle.grey,
        custom_id="persistent_view:grey",
    )
    async def grey(self, button: discord.ui.Button, interaction: discord.Interaction):

        if self.player.loop == "當前歌曲":
            self.player.loop = "無"

        await self.player.stop()

        self.player.client.dispatch("dismusic_track_skip", self.player)
        await interaction.response.send_message("跳過 :track_next:", ephemeral=True)

    @discord.ui.button(
        label="暫停 ⏯️",
        style=discord.ButtonStyle.green,
        custom_id="persistent_view:green"
    )
    async def green(self, button: discord.ui.Button, interaction: discord.Interaction):
        if self.player.is_playing():

            if self.player.is_paused():
                await self.player.set_pause(pause=False)
                self.player.client.dispatch("dismusic_player_resume", self.player)
                return await interaction.response.send_message("播放 :musical_note: ", ephemeral=True)
            else:
                await self.player.set_pause(pause=True)
                self.player.client.dispatch("dismusic_player_pause", self.player)
                return await interaction.response.send_message("暫停 :pause_button: ", ephemeral=True)

        await interaction.response.send_message("沒有在播放任何音源", ephemeral=True)

    @discord.ui.button(
        label="停止播放 ⏹️",
        style=discord.ButtonStyle.red,
        custom_id="persistent_view:red"
    )
    async def red(self, button: discord.ui.Button, interaction: discord.Interaction):
        await self.player.destroy()
        await interaction.response.send_message("停止播放 :stop_button: ", ephemeral=True)
        self.player.client.dispatch("dismusic_player_stop", self.player)


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
            return await self.bound_channel.send(embed=embed, view=MusicControllerView(self))

        await ctx.send(embed=embed, view=MusicControllerView(self))
