import asyncio

import async_timeout
import wavelink
from discord import ClientException, ApplicationContext, Member, Message, message_command, user_command
from discord.ext import commands
from wavelink import (
    LavalinkException,
    LoadTrackError,
    SoundCloudTrack,
    YouTubeMusicTrack,
    YouTubePlaylist,
    YouTubeTrack,
)
from wavelink.ext import spotify
from wavelink.ext.spotify import SpotifyTrack

from ._classes import Provider
from .checks import voice_channel_player, voice_connected
from .errors import MustBeSameChannel
from .paginator import Paginator
from .player import DisPlayer


class Music(commands.Cog):
    """Music commands"""

    def __init__(self, bot):
        self.bot: commands.Bot = bot
        self.bot.loop.create_task(self.start_nodes())

    def get_nodes(self):
        return sorted(wavelink.NodePool._nodes.values(), key=lambda n: len(n.players))

    async def play_track(self, ctx: commands.Context, query: str, provider=None):
        player: DisPlayer = ctx.voice_client

        if ctx.author.voice.channel.id != player.channel.id:
            raise MustBeSameChannel("你跟偶不在同個頻率上 嘖嘖")

        track_providers = {
            "yt": YouTubeTrack,
            "ytpl": YouTubePlaylist,
            "ytmusic": YouTubeMusicTrack,
            "soundcloud": SoundCloudTrack,
            "spotify": SpotifyTrack,
        }

        query = query.strip("<>")
        msg = await ctx.send(f"搜尋 `{query}` :mag_right:")

        track_provider = provider if provider else player.track_provider

        if track_provider == "yt" and "playlist" in query:
            provider = "ytpl"

        provider: Provider = track_providers.get(provider) if provider else track_providers.get(player.track_provider)

        nodes = self.get_nodes()

        tracks = list()

        for node in nodes:
            try:
                with async_timeout.timeout(20):
                    tracks = await provider.search(query, node=node)
                    break
            except asyncio.TimeoutError:
                self.bot.dispatch("dismusic_node_fail", node)
                wavelink.NodePool._nodes.pop(node.identifier)
                continue
            except (LavalinkException, LoadTrackError):
                continue

        if not tracks:
            return await msg.edit("找不到指定的歌曲或播放清單")

        if isinstance(tracks, YouTubePlaylist):
            tracks = tracks.tracks
            for track in tracks:
                await player.queue.put(track)

            await msg.edit(content=f"增加 `{len(tracks)}` 首到播放列")
        else:
            track = tracks[0]

            await msg.edit(content=f"增加 `{track.title}` 到播放列")
            await player.queue.put(track)

        if not player.is_playing():
            await player.do_next()

    async def start_nodes(self):
        await self.bot.wait_until_ready()
        spotify_credential = getattr(self.bot, "spotify_credentials", {"client_id": "", "client_secret": ""})

        for config in self.bot.lavalink_nodes:
            try:
                node: wavelink.Node = await wavelink.NodePool.create_node(
                    bot=self.bot,
                    **config,
                    spotify_client=spotify.SpotifyClient(**spotify_credential),
                )
                print(f"[dismusic] INFO - Created node: {node.identifier}")
            except Exception:
                print(f"[dismusic] ERROR - Failed to create node {config['host']}:{config['port']}")

    @commands.command(aliases=["con", "join"])
    @voice_connected()
    async def connect(self, ctx: commands.Context):
        """Connect the player"""
        if ctx.voice_client:
            return

        msg = await ctx.send(f"加入到 **`{ctx.author.voice.channel}`**")

        try:
            player: DisPlayer = await ctx.author.voice.channel.connect(cls=DisPlayer)
            self.bot.dispatch("dismusic_player_connect", player)
        except (asyncio.TimeoutError, ClientException):
            return await msg.edit(content="無法加入語音")

        player.bound_channel = ctx.channel
        player.bot = self.bot

        await msg.edit(content=f"加入到 **`{player.channel.name}`**")

    @commands.group(aliases=["p", "P", "PLAY"], invoke_without_command=True)
    @voice_connected()
    async def play(self, ctx: commands.Context, *, query: str):
        """Play or add song to queue (Defaults to YouTube)"""
        await ctx.invoke(self.connect)
        await self.play_track(ctx, query)

    @play.command(aliases=["yt"])
    @voice_connected()
    async def youtube(self, ctx: commands.Context, *, query: str):
        """Play a YouTube track"""
        await ctx.invoke(self.connect)
        await self.play_track(ctx, query, "yt")
        
    @play.command(aliases=["ytpl"])
    @voice_connected()
    async def youtubeplaylist(self, ctx: commands.Context, *, query: str):
        """Play a YouTube track"""
        await ctx.invoke(self.connect)
        await self.play_track(ctx, query, "ytpl")

    @play.command(aliases=["ytmusic"])
    @voice_connected()
    async def youtubemusic(self, ctx: commands.Context, *, query: str):
        """Play a YouTubeMusic track"""
        await ctx.invoke(self.connect)
        await self.play_track(ctx, query, "ytmusic")

    @play.command(aliases=["sc"])
    @voice_connected()
    async def soundcloud(self, ctx: commands.Context, *, query: str):
        """Play a SoundCloud track"""
        await ctx.invoke(self.connect)
        await self.play_track(ctx, query, "soundcloud")

    @play.command(aliases=["sp"])
    @voice_connected()
    async def spotify(self, ctx: commands.Context, *, query: str):
        """play a spotify track"""
        await ctx.invoke(self.connect)
        await self.play_track(ctx, query, "spotify")

    @commands.command(aliases=["vol"])
    @voice_channel_player()
    async def volume(self, ctx: commands.Context, vol: int, forced=False):
        """Set volume"""
        player: DisPlayer = ctx.voice_client

        if vol < 0:
            return await ctx.send("音量必須大於0")

        if vol > 100 and not forced:
            return await ctx.send("音量必須小於100")

        await player.set_volume(vol)
        await ctx.send(f"音量設定為 {vol} :loud_sound:")

    @commands.command(aliases=["disconnect", "dc", "leave"])
    @voice_channel_player()
    async def stop(self, ctx: commands.Context):
        """Stop the player"""
        player: DisPlayer = ctx.voice_client

        await player.destroy()
        await ctx.send("停止播放 :stop_button: ")
        self.bot.dispatch("dismusic_player_stop", player)

    @commands.command()
    @voice_channel_player()
    async def pause(self, ctx: commands.Context):
        """Pause the player"""
        player: DisPlayer = ctx.voice_client

        if player.is_playing():
            if player.is_paused():
                return await ctx.send("播放已經暫停")

            await player.set_pause(pause=True)
            self.bot.dispatch("dismusic_player_pause", player)
            return await ctx.send("暫停 :pause_button: ")

        await ctx.send("沒有在播放任何音源")

    @commands.command()
    @voice_channel_player()
    async def resume(self, ctx: commands.Context):
        """Resume the player"""
        player: DisPlayer = ctx.voice_client

        if player.is_playing():
            if not player.is_paused():
                return await ctx.send("正在播放中")

            await player.set_pause(pause=False)
            self.bot.dispatch("dismusic_player_resume", player)
            return await ctx.send("播放 :musical_note: ")

        await ctx.send("沒有在播放任何音源")

    @commands.command()
    @voice_channel_player()
    async def skip(self, ctx: commands.Context):
        """Skip to next song in the queue."""
        player: DisPlayer = ctx.voice_client

        if player.loop == "當前歌曲":
            player.loop = "無"

        await player.stop()

        self.bot.dispatch("dismusic_track_skip", player)
        await ctx.send("跳過 :track_next:")

    @commands.command()
    @voice_channel_player()
    async def seek(self, ctx: commands.Context, seconds: int):
        """Seek the player backward or forward"""
        player: DisPlayer = ctx.voice_client

        if player.is_playing():
            old_position = player.position
            position = old_position + seconds
            if position > player.source.length:
                return await ctx.send("超出歌曲時間長度")

            if position < 0:
                position = 0

            await player.seek(position * 1000)
            self.bot.dispatch("dismusic_player_seek", player, old_position, position)
            return await ctx.send(f"快轉到 {seconds} 秒 :fast_forward: ")

        await ctx.send("沒有在播放任何音源")

    @commands.command()
    @voice_channel_player()
    async def loop(self, ctx: commands.Context, loop_type: str = None):
        """Set loop to `無`, `當前歌曲` 或 `播放列表`"""
        player: DisPlayer = ctx.voice_client

        result = await player.set_loop(loop_type)
        await ctx.send(f"循環播放設定為 {result} :repeat: ")

    @commands.command(aliases=["q"])
    @voice_channel_player()
    async def queue(self, ctx: commands.Context):
        """Player queue"""
        player: DisPlayer = ctx.voice_client

        if len(player.queue._queue) < 1:
            return await ctx.send("沒有音樂在播放列")

        paginator = Paginator(ctx, player)
        await paginator.start()

    @commands.command(aliases=["np", "NP", "now", "NOW"])
    @voice_channel_player()
    async def nowplaying(self, ctx: commands.Context):
        """Currently playing song information"""
        player: DisPlayer = ctx.voice_client
        await player.invoke_player(ctx)

    @message_command(name="播放此首歌")
    @voice_connected()
    async def play_for_message(self, ctx: ApplicationContext, message: Message):
        """Play history song from message"""
        if message.embeds:
            await ctx.respond("測試版： 嘗試播放中...")
            await ctx.invoke(self.connect)
            await self.play_track(ctx, message.embeds[0].url)
        else:
            await ctx.respond("測試版： 此訊息不是播放過的歌曲")

    @user_command(name="⏯")
    @voice_channel_player()
    async def pause_or_resume(self, ctx: ApplicationContext, member: Member):
        """Pause or Resume the Player"""
        if member.id == self.bot.application_id:
            player: DisPlayer = ctx.voice_client

            if player.is_playing():

                if player.is_paused():
                    await player.set_pause(pause=False)
                    self.bot.dispatch("dismusic_player_resume", player)
                    return await ctx.respond("播放 :musical_note: ")
                else:
                    await player.set_pause(pause=True)
                    self.bot.dispatch("dismusic_player_pause", player)
                    return await ctx.respond("暫停 :pause_button: ")

            await ctx.respond("沒有在播放任何音源")
        else:
            await ctx.respond("必須在音樂機器人右鍵操作此指令")
